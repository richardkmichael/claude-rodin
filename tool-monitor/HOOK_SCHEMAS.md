# Claude Code Tool Hook Schemas

This document provides comprehensive JSON schemas for all Claude Code tool hooks captured through PreToolUse and PostToolUse events.

## Base Schema

All hook payloads extend this common base schema:

### PreToolUse Base Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "session_id": {"type": "string"},
    "transcript_path": {"type": "string"},
    "cwd": {"type": "string"},
    "hook_event_name": {"const": "PreToolUse"},
    "tool_name": {"type": "string"},
    "tool_input": {"type": "object"}
  },
  "required": ["session_id", "transcript_path", "cwd", "hook_event_name", "tool_name", "tool_input"]
}
```

### PostToolUse Base Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "session_id": {"type": "string"},
    "transcript_path": {"type": "string"},
    "cwd": {"type": "string"},
    "hook_event_name": {"const": "PostToolUse"},
    "tool_name": {"type": "string"},
    "tool_input": {"type": "object"},
    "tool_response": {
      "oneOf": [
        {"type": "string"},
        {"type": "object"},
        {"type": "array"}
      ]
    }
  },
  "required": ["session_id", "transcript_path", "cwd", "hook_event_name", "tool_name", "tool_input", "tool_response"]
}
```

## Tool-Specific Input/Output Schemas

Each tool extends the base schema with specific `tool_input` and `tool_response` structures.

**Note on Response Types:**
- **String responses**: Some tools (LS, Write, WebFetch) return plain strings
- **Object responses**: Most tools return structured objects with multiple fields
- **Array responses**: Some tools (NotebookRead) return arrays of objects
- The base schema uses a union type (`oneOf`) to accommodate these variations

### Bash Tool

**tool_input:**
```json
{
  "command": {"type": "string", "required": true},
  "description": {"type": "string", "required": true},
  "timeout": {"type": "number", "optional": true}
}
```

**tool_response:**
```json
{
  "stdout": {"type": "string"},
  "stderr": {"type": "string"},
  "interrupted": {"type": "boolean"},
  "isImage": {"type": "boolean"}
}
```

### Edit Tool

**tool_input:**
```json
{
  "file_path": {"type": "string", "required": true},
  "old_string": {"type": "string", "required": true},
  "new_string": {"type": "string", "required": true},
  "replace_all": {"type": "boolean", "default": false}
}
```

**tool_response:**
```json
{
  "filePath": {"type": "string"},
  "oldString": {"type": "string"},
  "newString": {"type": "string"},
  "originalFile": {"type": "string"},
  "structuredPatch": {
    "type": "array",
    "items": {
      "oldStart": {"type": "number"},
      "oldLines": {"type": "number"},
      "newStart": {"type": "number"},
      "newLines": {"type": "number"},
      "lines": {"type": "array", "items": {"type": "string"}}
    }
  },
  "userModified": {"type": "boolean"},
  "replaceAll": {"type": "boolean"}
}
```

### Glob Tool

**tool_input:**
```json
{
  "pattern": {"type": "string", "required": true},
  "path": {"type": "string", "optional": true}
}
```

**tool_response:**
```json
{
  "filenames": {"type": "array", "items": {"type": "string"}},
  "durationMs": {"type": "number"},
  "numFiles": {"type": "number"},
  "truncated": {"type": "boolean"}
}
```

### Grep Tool

**tool_input:**
```json
{
  "pattern": {"type": "string", "required": true},
  "output_mode": {"type": "string", "enum": ["content", "files_with_matches", "count"], "default": "files_with_matches"},
  "path": {"type": "string", "optional": true},
  "glob": {"type": "string", "optional": true},
  "type": {"type": "string", "optional": true},
  "-i": {"type": "boolean", "optional": true},
  "-n": {"type": "boolean", "optional": true},
  "-A": {"type": "number", "optional": true},
  "-B": {"type": "number", "optional": true},
  "-C": {"type": "number", "optional": true},
  "multiline": {"type": "boolean", "optional": true},
  "head_limit": {"type": "number", "optional": true}
}
```

**tool_response:**
```json
{
  "mode": {"type": "string"},
  "filenames": {"type": "array", "items": {"type": "string"}},
  "numFiles": {"type": "number"}
}
```

### LS Tool

**tool_input:**
```json
{
  "path": {"type": "string", "required": true},
  "ignore": {"type": "array", "items": {"type": "string"}, "optional": true}
}
```

**tool_response:**
```json
string
```

### Read Tool

**tool_input:**
```json
{
  "file_path": {"type": "string", "required": true},
  "limit": {"type": "number", "optional": true},
  "offset": {"type": "number", "optional": true}
}
```

**tool_response:**
```json
{
  "type": {"type": "string"},
  "file": {
    "filePath": {"type": "string"},
    "content": {"type": "string"},
    "numLines": {"type": "number"},
    "startLine": {"type": "number"},
    "totalLines": {"type": "number"}
  }
}
```

### Write Tool

**tool_input:**
```json
{
  "file_path": {"type": "string", "required": true},
  "content": {"type": "string", "required": true}
}
```

**tool_response:**
```json
string
```

### Task Tool

**tool_input:**
```json
{
  "description": {"type": "string", "required": true},
  "prompt": {"type": "string", "required": true},
  "subagent_type": {"type": "string", "required": true}
}
```

**tool_response:**
```json
{
  "content": {
    "type": "array",
    "items": {
      "type": {"type": "string"},
      "text": {"type": "string"}
    }
  },
  "totalDurationMs": {"type": "number"},
  "totalTokens": {"type": "number"},
  "totalToolUseCount": {"type": "number"},
  "usage": {
    "input_tokens": {"type": "number"},
    "cache_creation_input_tokens": {"type": "number"},
    "cache_read_input_tokens": {"type": "number"},
    "output_tokens": {"type": "number"},
    "service_tier": {"type": "string"}
  }
}
```

### WebSearch Tool

**tool_input:**
```json
{
  "query": {"type": "string", "required": true},
  "allowed_domains": {"type": "array", "items": {"type": "string"}, "optional": true},
  "blocked_domains": {"type": "array", "items": {"type": "string"}, "optional": true}
}
```

**tool_response:**
```json
{
  "query": {"type": "string"},
  "results": {
    "type": "array",
    "items": {
      "tool_use_id": {"type": "string"},
      "content": {
        "type": "array",
        "items": {
          "title": {"type": "string"},
          "url": {"type": "string"}
        }
      }
    }
  },
  "durationSeconds": {"type": "number"}
}
```

### WebFetch Tool

**tool_input:**
```json
{
  "url": {"type": "string", "format": "uri", "required": true},
  "prompt": {"type": "string", "required": true}
}
```

**tool_response:**
```json
string
```

### NotebookRead Tool

**tool_input:**
```json
{
  "notebook_path": {"type": "string", "required": true},
  "cell_id": {"type": "string", "optional": true}
}
```

**tool_response:**
```json
{
  "type": "array",
  "items": {
    "cellType": {"type": "string"},
    "source": {"type": "string"},
    "cell_id": {"type": "string"},
    "language": {"type": "string"}
  }
}
```

### TodoWrite Tool

**tool_input:**
```json
{
  "todos": {
    "type": "array",
    "items": {
      "content": {"type": "string", "required": true},
      "status": {"type": "string", "enum": ["pending", "in_progress", "completed"], "required": true},
      "priority": {"type": "string", "enum": ["high", "medium", "low"], "required": true},
      "id": {"type": "string", "required": true}
    },
    "required": true
  }
}
```

**tool_response:**
```json
{
  "oldTodos": {
    "type": "array",
    "items": {
      "content": {"type": "string"},
      "status": {"type": "string"},
      "priority": {"type": "string"},
      "id": {"type": "string"}
    }
  },
  "newTodos": {
    "type": "array",
    "items": {
      "content": {"type": "string"},
      "status": {"type": "string"},
      "priority": {"type": "string"},
      "id": {"type": "string"}
    }
  }
}
```

## Tool Categories

### File Operations
- **Read**: Read file contents
- **Write**: Create/overwrite file
- **Edit**: Modify existing file content
- **NotebookRead**: Read Jupyter notebook cells

### Search Operations
- **Glob**: Find files by pattern
- **Grep**: Search file contents

### System Operations  
- **Bash**: Execute shell commands
- **LS**: List directory contents

### Web Operations
- **WebSearch**: Search the web
- **WebFetch**: Fetch and analyze web content

### Workflow Operations
- **Task**: Launch subagent tasks
- **TodoWrite**: Manage task lists

## Usage Notes

1. **session_id**: Unique identifier for the Claude Code session
2. **transcript_path**: Path to the session transcript file 
3. **cwd**: Current working directory when tool was executed
4. **hook_event_name**: Either "PreToolUse" or "PostToolUse"
5. **tool_name**: Name of the tool being executed
6. **tool_input**: Tool-specific input parameters (schemas above)
7. **tool_response**: Tool-specific response data (only in PostToolUse, schemas above)

## Schema Version

This schema documentation corresponds to Claude Code tool hooks as captured in August 2025. Tool schemas may evolve over time as new features are added.
