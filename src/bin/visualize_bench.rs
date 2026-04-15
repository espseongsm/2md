use plotly::{Plot, Bar, Layout};

fn main() {
    let files = vec![
        "Soonmo_CV",
        "Press Release",
        "Guide",
        "Insurance",
        "Public Notice",
        "Agentic Design",
    ];

    let markitdown_times = vec![0.53, 0.59, 1.26, 2.27, 3.61, 56.79];
    let twomd_times = vec![0.01, 0.02, 0.13, 0.09, 0.58, 3.14];

    // In plotly-rs 0.14, Bar is a wrapper around a trace.
    // To set the name, we use the .name() method which returns the object (builder pattern).
    let trace_markitdown = Bar::new(files.clone(), markitdown_times)
        .name("MarkItDown");

    let trace_twomd = Bar::new(files, twomd_times)
        .name("2md");

    let mut plot = Plot::new();
    plot.add_trace(trace_markitdown);
    plot.add_trace(trace_twomd);

    let layout = Layout::default();
    plot.set_layout(layout);

    plot.write_html("benchmark/benchmark_chart.html");

    if let Err(e) = plot.write_image("benchmark/benchmark_chart.png", plotly::ImageFormat::PNG, 800, 600, 1.0) {
        eprintln!("Static image export failed: {}. Make sure a webdriver is installed.", e);
    } else {
        println!("Chart saved to benchmark/benchmark_chart.png");
    }
}
