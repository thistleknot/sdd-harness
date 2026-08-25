Build a 3D tower defense game from scratch in THIS directory. Requirements:

- C++ with SDL2 for windowing and OpenGL 3.3+ for rendering
- Custom engine — no Unity, Godot, or framework dependencies
- Enemies spawn at a start point, pathfind through a 3D environment to an exit
- Player clicks to place towers that shoot projectiles at enemies in range
- 3 waves of increasing enemy count, lives system, win/lose state
- Must compile on Windows x64 with MSVC and run without crashing

SDL2 is already in this directory at ./SDL2/ (includes at SDL2/include/SDL2/, libs at SDL2/lib/x64/)

Write ALL source files. Create a CMakeLists.txt. Then compile with:
  cmake -S . -B build -A x64 && cmake --build build --config Release
Fix any compile errors. Confirm the exe runs.
