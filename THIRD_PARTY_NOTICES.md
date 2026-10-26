# Third-Party Notices & Attribution

SubagentBridge (Simpul) is an independent, clean-room implementation written in Python.
Its architecture and design incorporate principles and inspiration from open-source
research references. Proper credit, provenance, and license obligations are recorded below.

---

## 1. Cindy (Orca Orchestration Core Reference)

- **Product / Project:** Cindy
- **Copyright:** Copyright 2026 XD Inc.
- **Repository:** https://github.com/makecindy/cindy
- **Pinned Research Commit:** `b7e46bcbbe41eeee2f16381fef00df61a31a3b8b`
- **License:** Apache License, Version 2.0

### Provenance & Clean-Room Source Audit

1. **Architectural Inspiration:**
   Cindy's Orca orchestration-core served as an architectural reference and design study
   for Simpul's multi-worker agent coordination. Specifically, concepts studied include:
   - Lead Session vs Worker Session role separation.
   - Structured inter-agent task dispatching and queue state transitions.
   - Worker lifecycle status states and interruption semantics.
   - Git worktree workspace isolation.
   - Structured handoff evidence and crash recovery state rehydration.

2. **Independently Implemented Behavior:**
   All runtime implementations in Simpul (`subagentbridge/`) were created independently
   from scratch in Python 3.11+, using Python standard library primitives (`sqlite3`,
   `subprocess`, `hashlib`, `uuid`, `dataclasses`) and native MCP protocols. No source
   files were copied, transliterated, vendored, or directly adapted from Cindy's TypeScript
   codebase.

3. **Relationship:**
   Simpul is not a fork or derivative distribution of Cindy. Cindy is credited here in
   full as an architectural provenance and academic/engineering reference.

### Apache-2.0 License Notice

```
                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   Copyright 2026 XD Inc.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
```

---

## 2. antigravity-mcp

- **Author:** Inferno-Aditya
- **Repository:** https://github.com/Inferno-Aditya/antigravity-mcp
- **License:** MIT

```
MIT License

Copyright (c) 2025 Inferno-Aditya

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
