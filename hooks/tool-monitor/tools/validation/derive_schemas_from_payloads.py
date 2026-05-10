#!/usr/bin/env python
"""
Derive JSON schemas from actual tool payloads in the database.

This tool analyzes real payloads to understand the actual structure of tool events,
which can help when Claude Code tool schemas change or when documenting undocumented tools.

Usage:
    # Analyze all tools and show schema differences
    python tools/validation/derive_schemas_from_payloads.py monitor.db
    
    # Analyze specific tool
    python tools/validation/derive_schemas_from_payloads.py monitor.db --tool Bash
    
    # Generate schema files from analysis
    python tools/validation/derive_schemas_from_payloads.py monitor.db --generate-schemas
"""

import json
import sqlite3
import sys
from collections import defaultdict, Counter
from typing import Dict, Any, Set, List
from pathlib import Path

def analyze_json_structure(obj: Any, path: str = "$") -> Dict[str, Set[str]]:
    """Analyze JSON structure and return field paths with their types."""
    structure = defaultdict(set)
    
    if isinstance(obj, dict):
        for key, value in obj.items():
            field_path = f"{path}.{key}" if path != "$" else f"$.{key}"
            structure[field_path].add(type(value).__name__)
            
            # Recurse into nested structures
            nested = analyze_json_structure(value, field_path)
            for nested_path, types in nested.items():
                structure[nested_path].update(types)
                
    elif isinstance(obj, list) and obj:
        # Analyze first few items in arrays to understand structure
        for i, item in enumerate(obj[:3]):  # Sample first 3 items
            item_path = f"{path}[{i}]"
            structure[item_path].add(type(item).__name__)
            
            nested = analyze_json_structure(item, item_path)
            for nested_path, types in nested.items():
                structure[nested_path].update(types)
    
    return structure

def get_sample_payloads(conn: sqlite3.Connection, tool_name: str = None, hook_event: str = None, limit: int = 10) -> List[Dict]:
    """Get sample payloads for analysis."""
    cursor = conn.cursor()
    
    where_clauses = []
    params = []
    
    if tool_name:
        where_clauses.append("tool_name = ?")
        params.append(tool_name)
    
    if hook_event:
        where_clauses.append("hook_event_name = ?")  
        params.append(hook_event)
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    cursor.execute(f"""
        SELECT tool_name, hook_event_name, payload
        FROM tool_events 
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT ?
    """, params + [limit])
    
    results = []
    for row in cursor.fetchall():
        try:
            payload = json.loads(row[2])
            results.append({
                'tool_name': row[0],
                'hook_event_name': row[1], 
                'payload': payload
            })
        except json.JSONDecodeError:
            continue
    
    return results

def derive_schema_from_samples(samples: List[Dict]) -> Dict[str, Any]:
    """Derive a JSON schema from sample payloads."""
    if not samples:
        return {}
    
    # Analyze structure of all samples
    all_structures = []
    for sample in samples:
        structure = analyze_json_structure(sample['payload'])
        all_structures.append(structure)
    
    # Find common fields and their types
    field_types = defaultdict(Counter)
    for structure in all_structures:
        for field_path, types in structure.items():
            for type_name in types:
                field_types[field_path][type_name] += 1
    
    # Build schema
    schema = {
        "type": "object",
        "description": f"Derived from {len(samples)} sample payloads",
        "properties": {},
        "sample_size": len(samples)
    }
    
    # Group fields by their root level
    root_fields = defaultdict(dict)
    for field_path, type_counter in field_types.items():
        parts = field_path.split('.')
        if len(parts) >= 2:  # $.field_name
            field_name = parts[1]
            most_common_type = type_counter.most_common(1)[0][0]
            
            # Map Python types to JSON Schema types
            type_mapping = {
                'str': 'string',
                'int': 'number', 
                'float': 'number',
                'bool': 'boolean',
                'dict': 'object',
                'list': 'array',
                'NoneType': 'null'
            }
            
            json_type = type_mapping.get(most_common_type, 'string')
            frequency = type_counter[most_common_type] / len(samples)
            
            root_fields[field_name] = {
                "type": json_type,
                "frequency": frequency,
                "sample_types": dict(type_counter)
            }
    
    schema["properties"] = root_fields
    
    # Identify required fields (present in >80% of samples)
    required_fields = [
        field for field, info in root_fields.items() 
        if info["frequency"] > 0.8
    ]
    if required_fields:
        schema["required"] = required_fields
    
    return schema

def analyze_database(db_path: str, tool_name: str = None):
    """Analyze database and show derived schemas."""
    conn = sqlite3.connect(db_path)
    
    print(f"=== SCHEMA ANALYSIS: {db_path} ===\n")
    
    # Get tool usage stats
    cursor = conn.cursor()
    if tool_name:
        cursor.execute("SELECT tool_name, hook_event_name, COUNT(*) FROM tool_events WHERE tool_name = ? GROUP BY tool_name, hook_event_name", (tool_name,))
    else:
        cursor.execute("SELECT tool_name, hook_event_name, COUNT(*) FROM tool_events GROUP BY tool_name, hook_event_name ORDER BY tool_name, hook_event_name")
    
    tool_stats = cursor.fetchall()
    
    for tool, hook_event, count in tool_stats:
        print(f"## {tool} - {hook_event} ({count} events)")
        
        # Get samples and derive schema
        samples = get_sample_payloads(conn, tool, hook_event, limit=min(count, 20))
        derived_schema = derive_schema_from_samples(samples)
        
        if derived_schema:
            print(f"📊 Analyzed {derived_schema['sample_size']} samples")
            print("🔍 Derived structure:")
            
            for field, info in derived_schema.get("properties", {}).items():
                freq_pct = int(info["frequency"] * 100)
                types_str = ", ".join([f"{t}({c})" for t, c in info["sample_types"].items()])
                print(f"  {field}: {info['type']} ({freq_pct}% present, types: {types_str})")
            
            required = derived_schema.get("required", [])
            if required:
                print(f"✅ Required fields: {', '.join(required)}")
            
            print()
        else:
            print("❌ No valid samples found\n")
    
    conn.close()

def compare_with_existing_schemas(db_path: str, schemas_dir: str = "schemas"):
    """Compare derived schemas with existing schema files."""
    print("=== COMPARING WITH EXISTING SCHEMAS ===\n")
    
    schemas_path = Path(schemas_dir)
    if not schemas_path.exists():
        print(f"❌ Schemas directory not found: {schemas_path}")
        return
    
    conn = sqlite3.connect(db_path)
    
    # Get unique tool/hook combinations from database
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT tool_name, hook_event_name FROM tool_events ORDER BY tool_name, hook_event_name")
    
    for tool_name, hook_event in cursor.fetchall():
        # Generate expected schema filename
        hook_snake = hook_event.replace("ToolUse", "_tool_use")
        tool_lower = tool_name.lower()
        schema_filename = f"{tool_lower}-{hook_snake.lower()}.json"
        schema_path = schemas_path / schema_filename
        
        print(f"## {tool_name} - {hook_event}")
        
        if schema_path.exists():
            # Load existing schema
            with open(schema_path) as f:
                existing_schema = json.load(f)
            
            # Derive schema from database
            samples = get_sample_payloads(conn, tool_name, hook_event, limit=10)
            derived_schema = derive_schema_from_samples(samples)
            
            # Compare
            existing_fields = set(existing_schema.get("properties", {}).keys())
            derived_fields = set(derived_schema.get("properties", {}).keys())
            
            if existing_fields == derived_fields:
                print("✅ Fields match existing schema")
            else:
                missing = existing_fields - derived_fields
                extra = derived_fields - existing_fields
                
                if missing:
                    print(f"⚠️  Fields in schema but not in data: {missing}")
                if extra:
                    print(f"🆕 Fields in data but not in schema: {extra}")
        else:
            print(f"❌ Schema file missing: {schema_filename}")
        
        print()
    
    conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python derive_schemas_from_payloads.py <database.db>")
        print("  python derive_schemas_from_payloads.py <database.db> --tool <ToolName>")
        print("  python derive_schemas_from_payloads.py <database.db> --compare")
        print()
        print("Examples:")
        print("  python derive_schemas_from_payloads.py monitor.db")
        print("  python derive_schemas_from_payloads.py monitor.db --tool Bash")
        print("  python derive_schemas_from_payloads.py monitor.db --compare")
        sys.exit(1)
    
    db_path = sys.argv[1]
    
    if "--compare" in sys.argv:
        compare_with_existing_schemas(db_path)
    elif "--tool" in sys.argv:
        tool_idx = sys.argv.index("--tool") + 1
        if tool_idx < len(sys.argv):
            analyze_database(db_path, sys.argv[tool_idx])
        else:
            print("Error: --tool requires a tool name")
            sys.exit(1)
    else:
        analyze_database(db_path)