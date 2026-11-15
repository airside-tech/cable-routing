# 2D Map (Rust / egui)

This project is a Rust port of the 2D cable-planning editor, built with `egui`.

## Run it

```bash
cd 2D-map-rust
cargo run
```

## Notes

- The app keeps a simple, tidy Rust structure with separate modules for the domain model, geometry, and UI logic.
- It includes a minimal room editor, object placement, cable drafting, and drag interactions for the active room.
