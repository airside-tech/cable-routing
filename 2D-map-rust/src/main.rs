mod app;
mod geometry;
mod model;

fn main() -> eframe::Result<()> {
    let native_options = eframe::NativeOptions {
        viewport: eframe::egui::ViewportBuilder::default().with_inner_size([1200.0, 800.0]),
        ..Default::default()
    };

    eframe::run_native(
        "2D Cable Planning Map",
        native_options,
        Box::new(|_cc| Ok(Box::new(app::CableMapApp::default()))),
    )
}
