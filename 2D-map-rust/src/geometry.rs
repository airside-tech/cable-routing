pub fn clamp(value: f32, min: f32, max: f32) -> f32 {
    value.clamp(min, max)
}

pub fn round(value: f32) -> f32 {
    (value * 100.0).round() / 100.0
}
