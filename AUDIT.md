# Audit — The Iron Maw

<!-- REGEN:START — everything here is rewritten at each phase boundary -->
## Scope & method
- **Commit:** 58656c1c0239ad8d1d43d34fb9a8a09e14c4a090
- **Date:** 2026-09-07
- **Languages:** Python
- **Files Audited:** 11 / 11
- **Tools Run:** ruff, mypy, pytest
- **Model:** Default
- **What was NOT covered:** Runtime testing, load testing
## Executive summary
The codebase has significant gaps in error handling around its core IO operations. The game's save system and storylet loading mechanism use unsafe bare exceptions or lack exception handling entirely when parsing JSON data, making the application vulnerable to corrupted files causing silent failures or hard crashes.

## Findings by severity
| ID | Location | Category | Claim | Confidence |
|---|---|---|---|---|
| F001 | save_system.py:191 | error-handling | Bare except catches all exceptions during save loading, potentially masking serious errors. | confirmed |
| F002 | save_system.py:282 | error-handling | Bare except catches all exceptions during save loading, potentially masking serious errors. | confirmed |
| F003 | save_system.py:404 | error-handling | Bare except catches all exceptions during save loading, potentially masking serious errors. | confirmed |
| F004 | save_system.py:465 | error-handling | Bare except catches all exceptions during save loading, potentially masking serious errors. | confirmed |
| F005 | storylets.py:340 | error-handling | No exception handling when loading JSON from files in directory. | confirmed |
| F006 | storylets.py:496 | error-handling | No exception handling when importing JSON from a file. | confirmed |

## Systemic themes
- **Inadequate Error Handling in Data Loading:** Both `save_system.py` and `storylets.py` fail to properly handle malformed JSON files. `save_system.py` uses bare `except:` clauses that mask real errors, while `storylets.py` lacks exception handling entirely, leading to application crashes on invalid input.

## Design opinions
- **State Management:** The game state management in `engine.py` is quite centralized. Breaking it up into smaller, more focused components might make it easier to maintain and test.

## Strengths
- **Modular Component System:** The entity component system in `entities/components.py` provides a flexible way to compose game objects.

## Verification & limitations
- Findings are based on static analysis of the source code. No runtime testing was performed to verify the exact behavior under error conditions.
<!-- REGEN:END -->

## Findings Log

### F001 — [MEDIUM] save_system.py:191 — Bare except catches all exceptions during save loading, potentially masking serious errors.
**Category:** error-handling  **Confidence:** confirmed
**Code:**
```python
            try:
                data_str = self._decompress_data(raw_data)
                data = json.loads(data_str)
                compressed = True
            except:
                data = json.loads(raw_data.decode('utf-8'))
                compressed = False
```
**Trigger:** Any exception (like KeyboardInterrupt or a real JSONDecodeError) during decompression or parsing.
**Impact:** The exception is swallowed, and the code incorrectly assumes the data is just uncompressed, potentially leading to a crash or corrupted data further down.
**Fix:** Change `except:` to `except (zlib.error, json.JSONDecodeError):` or similar specific exceptions.

### F002 — [MEDIUM] save_system.py:282 — Bare except catches all exceptions during save loading, potentially masking serious errors.
**Category:** error-handling  **Confidence:** confirmed
**Code:**
```python
            try:
                data_str = self._decompress_data(raw_data)
                data = json.loads(data_str)
            except:
                data = json.loads(raw_data.decode('utf-8'))
```
**Trigger:** Any exception (like KeyboardInterrupt or a real JSONDecodeError) during decompression or parsing.
**Impact:** The exception is swallowed, and the code incorrectly assumes the data is just uncompressed, potentially leading to a crash or corrupted data further down.
**Fix:** Change `except:` to `except (zlib.error, json.JSONDecodeError):` or similar specific exceptions.

### F003 — [MEDIUM] save_system.py:404 — Bare except catches all exceptions during save loading, potentially masking serious errors.
**Category:** error-handling  **Confidence:** confirmed
**Code:**
```python
            try:
                data_str = self._decompress_data(raw_data)
                data = json.loads(data_str)
            except:
                data = json.loads(raw_data.decode('utf-8'))
```
**Trigger:** Any exception (like KeyboardInterrupt or a real JSONDecodeError) during decompression or parsing.
**Impact:** The exception is swallowed, and the code incorrectly assumes the data is just uncompressed, potentially leading to a crash or corrupted data further down.
**Fix:** Change `except:` to `except (zlib.error, json.JSONDecodeError):` or similar specific exceptions.

### F004 — [MEDIUM] save_system.py:465 — Bare except catches all exceptions during save loading, potentially masking serious errors.
**Category:** error-handling  **Confidence:** confirmed
**Code:**
```python
            try:
                data_str = self._decompress_data(raw_data)
                data = json.loads(data_str)
            except:
                data = json.loads(raw_data.decode('utf-8'))
```
**Trigger:** Any exception (like KeyboardInterrupt or a real JSONDecodeError) during decompression or parsing.
**Impact:** The exception is swallowed, and the code incorrectly assumes the data is just uncompressed, potentially leading to a crash or corrupted data further down.
**Fix:** Change `except:` to `except (zlib.error, json.JSONDecodeError):` or similar specific exceptions.
### F005 — [MEDIUM] storylets.py:340 — No exception handling when loading JSON from files in directory.
**Category:** error-handling  **Confidence:** confirmed
**Code:**
```python
                with open(file_path, 'r') as f:
                    data = json.load(f)
```
**Trigger:** A malformed JSON file in the storylets directory.
**Impact:** The entire application crashes during startup or storylet loading.
**Fix:** Wrap `json.load` in a `try...except json.JSONDecodeError:` block and log or ignore the corrupted file.

### F006 — [MEDIUM] storylets.py:496 — No exception handling when importing JSON from a file.
**Category:** error-handling  **Confidence:** confirmed
**Code:**
```python
        with open(file_path, 'r') as f:
            data = json.load(f)
```
**Trigger:** A malformed JSON file provided for import.
**Impact:** The application crashes instead of gracefully rejecting the file.
**Fix:** Wrap `json.load` in a `try...except json.JSONDecodeError:` block.
