"""CustomTkinter user interface for GridGemma Pro."""

from __future__ import annotations

import threading
import traceback
from tkinter import filedialog, messagebox

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from .defaults import CLIMATE_PRESETS, ECONOMIC_PRESETS, get_outputs_dir
from .export import (
    build_metadata,
    default_csv_filename,
    default_metadata_filename,
    export_metadata_json,
    export_pypsa_csv,
)
from .local_llm_client import (
    check_offline_ai_status,
    default_model_path,
    get_behavior_parameters,
    get_future_scenario_anomalies,
)
from .plotting import VIEW_FIRST_TWO_WEEKS, VIEW_FULL_YEAR, VIEW_PEAK_MONTH, plot_load_curve
from .schemas import EventAnomaly, GridInputs, LLMParameters, WebSnippet
from .synthesizer import calculate_statistics, synthesize_load_curve
from .validators import validate_inputs
from .web_context import get_future_scenario_context


class GridGemmaApp(ctk.CTk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("GridGemma Pro - S. INC")
        self.geometry("1250x750")
        self.minsize(1250, 750)

        self.current_df = None
        self.current_inputs: GridInputs | None = None
        self.current_parameters: LLMParameters | None = None
        self.current_metadata: dict | None = None
        self.current_view = VIEW_FIRST_TWO_WEEKS

        self.future_snippets: list[WebSnippet] = []
        self.future_event_anomalies: list[EventAnomaly] = []
        self.future_scenario_label = ""
        self.web_search_used = False
        self.scenario_local_model_used = False
        self.scenario_fallback_used = False

        self._build_layout()
        self._set_export_state(False)
        self._update_future_search_state()
        self._refresh_ai_status(show_popup=False)
        self._hide_snippets_panel()
        self._log("Ready. Normal synthesis is fully offline.")

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=0, minsize=390)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.left_panel = ctk.CTkScrollableFrame(self, corner_radius=0, width=390)
        self.left_panel.grid(row=0, column=0, sticky="nsew")
        self.left_panel.grid_columnconfigure(0, weight=1)

        self.right_panel = ctk.CTkFrame(self, corner_radius=0)
        self.right_panel.grid(row=0, column=1, sticky="nsew")
        self.right_panel.grid_columnconfigure(0, weight=1)
        self.right_panel.grid_rowconfigure(1, weight=1)

        self._build_left_panel()
        self._build_right_panel()

    def _build_left_panel(self) -> None:
        title = ctk.CTkLabel(
            self.left_panel,
            text="GridGemma Pro",
            font=ctk.CTkFont(size=26, weight="bold"),
        )
        title.grid(row=0, column=0, padx=22, pady=(20, 2), sticky="w")

        maker = ctk.CTkLabel(self.left_panel, text="by S. INC", text_color="#AAB2BF")
        maker.grid(row=1, column=0, padx=22, pady=(0, 10), sticky="w")

        self.country_entry = self._entry("Country/region", 2, "Ghana")
        self.year_entry = self._entry("Target year", 3, "2025")
        self.annual_entry = self._entry("Annual consumption TWh", 4, "25")
        self.peak_entry = self._entry("Peak demand MW", 5, "4500")

        self.climate_combo = self._combo("Climate profile", 6, CLIMATE_PRESETS)
        self.climate_combo.set(CLIMATE_PRESETS[1])
        self.economy_combo = self._combo("Economic profile", 7, ECONOMIC_PRESETS)
        self.economy_combo.set(ECONOMIC_PRESETS[-1])

        ctk.CTkLabel(self.left_panel, text="Local Gemma 4 model path").grid(
            row=16, column=0, padx=22, pady=(2, 3), sticky="w"
        )
        model_row = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        model_row.grid(row=17, column=0, padx=22, pady=(0, 8), sticky="ew")
        model_row.grid_columnconfigure(0, weight=1)
        self.model_path_entry = ctk.CTkEntry(model_row, height=32)
        discovered_model = default_model_path()
        if discovered_model.is_file():
            self.model_path_entry.insert(0, str(discovered_model))
        self.model_path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.browse_model_button = ctk.CTkButton(
            model_row,
            text="Browse Model",
            command=self._on_browse_model,
            width=116,
        )
        self.browse_model_button.grid(row=0, column=1)

        self.check_ai_button = ctk.CTkButton(
            self.left_panel,
            text="Check Local AI",
            command=lambda: self._refresh_ai_status(show_popup=True),
        )
        self.check_ai_button.grid(row=18, column=0, padx=22, pady=(4, 4), sticky="ew")

        self.download_help_button = ctk.CTkButton(
            self.left_panel,
            text="Download Instructions",
            command=self._show_download_instructions,
            fg_color="#4B5563",
        )
        self.download_help_button.grid(row=19, column=0, padx=22, pady=(0, 8), sticky="ew")

        ctk.CTkLabel(self.left_panel, text="Offline AI Status").grid(
            row=20, column=0, padx=22, pady=(0, 3), sticky="w"
        )
        self.ai_status_box = ctk.CTkTextbox(self.left_panel, height=118, wrap="word")
        self.ai_status_box.grid(row=21, column=0, padx=22, pady=(0, 10), sticky="ew")
        self.ai_status_box.configure(state="disabled")

        self.future_search_switch = ctk.CTkSwitch(
            self.left_panel,
            text="Enable online search for future project/news scenario",
            command=self._update_future_search_state,
            progress_color="#2D8CFF",
        )
        self.future_search_switch.grid(row=22, column=0, padx=22, pady=(8, 4), sticky="w")

        self.future_warning = ctk.CTkLabel(
            self.left_panel,
            text=(
                "This will search public web snippets for future energy projects or major "
                "events. It does not use cloud AI."
            ),
            text_color="#D19A66",
            wraplength=330,
            justify="left",
        )
        self.future_warning.grid(row=23, column=0, padx=22, pady=(0, 8), sticky="w")

        self.search_news_button = ctk.CTkButton(
            self.left_panel,
            text="Search Future Scenario News",
            command=self._on_search_future_news,
        )
        self.search_news_button.grid(row=24, column=0, padx=22, pady=(0, 12), sticky="ew")

        self.synthesize_button = ctk.CTkButton(
            self.left_panel,
            text="Synthesize Curve",
            command=self._on_synthesize,
            height=38,
        )
        self.synthesize_button.grid(row=25, column=0, padx=22, pady=(2, 8), sticky="ew")

        export_row = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        export_row.grid(row=26, column=0, padx=22, pady=(0, 8), sticky="ew")
        export_row.grid_columnconfigure((0, 1), weight=1)
        self.export_csv_button = ctk.CTkButton(
            export_row,
            text="Export PyPSA CSV",
            command=self._on_export_csv,
        )
        self.export_csv_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.export_json_button = ctk.CTkButton(
            export_row,
            text="Export Metadata JSON",
            command=self._on_export_metadata,
        )
        self.export_json_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))

        clear_button = ctk.CTkButton(
            self.left_panel,
            text="Clear",
            command=self._on_clear,
            fg_color="#4B5563",
        )
        clear_button.grid(row=27, column=0, padx=22, pady=(0, 14), sticky="ew")

        footer = ctk.CTkLabel(
            self.left_panel,
            text=(
                "GridGemma Pro by S. INC\n"
                "Offline synthetic load-curve generator for power systems research"
            ),
            text_color="#AAB2BF",
            justify="left",
            wraplength=330,
        )
        footer.grid(row=28, column=0, padx=22, pady=(4, 20), sticky="w")

    def _build_right_panel(self) -> None:
        top_bar = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 8))
        top_bar.grid_columnconfigure(3, weight=1)

        ctk.CTkButton(
            top_bar,
            text="First 2 weeks",
            command=lambda: self._set_view(VIEW_FIRST_TWO_WEEKS),
            width=120,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            top_bar,
            text="Peak month",
            command=lambda: self._set_view(VIEW_PEAK_MONTH),
            width=110,
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            top_bar,
            text="Full year overview",
            command=lambda: self._set_view(VIEW_FULL_YEAR),
            width=150,
        ).grid(row=0, column=2, padx=(0, 8))

        content = ctk.CTkFrame(self.right_panel, corner_radius=8)
        content.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)

        plot_frame = ctk.CTkFrame(content, corner_radius=8)
        plot_frame.grid(row=0, column=0, sticky="nsew", padx=(10, 6), pady=10)
        plot_frame.grid_columnconfigure(0, weight=1)
        plot_frame.grid_rowconfigure(0, weight=1)

        self.figure = Figure(figsize=(7.2, 4.8), dpi=100, facecolor="#1F2329")
        self.ax = self.figure.add_subplot(111)
        self._style_axis()
        self.ax.set_title("No curve synthesized yet")
        self.ax.set_xlabel("Snapshot")
        self.ax.set_ylabel("Load (MW)")
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self.canvas.draw()

        side = ctk.CTkFrame(content, corner_radius=8)
        side.grid(row=0, column=1, sticky="nsew", padx=(6, 10), pady=10)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(1, weight=1)
        side.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(side, text="Statistics", font=ctk.CTkFont(size=17, weight="bold")).grid(
            row=0, column=0, padx=12, pady=(12, 6), sticky="w"
        )
        self.stats_box = ctk.CTkTextbox(side, height=240, wrap="word")
        self.stats_box.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="nsew")
        self.stats_box.insert("1.0", "Synthesize a curve to see statistics.")
        self.stats_box.configure(state="disabled")

        self.snippets_label = ctk.CTkLabel(
            side, text="Future Scenario Snippets", font=ctk.CTkFont(size=17, weight="bold")
        )
        self.snippets_label.grid(row=2, column=0, padx=12, pady=(2, 6), sticky="w")
        self.snippets_box = ctk.CTkTextbox(side, height=180, wrap="word")
        self.snippets_box.grid(row=3, column=0, padx=12, pady=(0, 10), sticky="nsew")
        self.snippets_box.insert("1.0", "No future scenario search used.")
        self.snippets_box.configure(state="disabled")

        log_frame = ctk.CTkFrame(self.right_panel, corner_radius=8)
        log_frame.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        log_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_frame, text="Status Log", font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, padx=12, pady=(8, 2), sticky="w"
        )
        self.log_box = ctk.CTkTextbox(log_frame, height=105, wrap="word")
        self.log_box.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.log_box.configure(state="disabled")

    def _entry(self, label: str, row: int, default: str) -> ctk.CTkEntry:
        ctk.CTkLabel(self.left_panel, text=label).grid(
            row=row * 2, column=0, padx=22, pady=(2, 3), sticky="w"
        )
        entry = ctk.CTkEntry(self.left_panel, height=32)
        entry.grid(row=row * 2 + 1, column=0, padx=22, pady=(0, 8), sticky="ew")
        if default:
            entry.insert(0, default)
        return entry

    def _combo(self, label: str, row: int, values: list[str]) -> ctk.CTkComboBox:
        ctk.CTkLabel(self.left_panel, text=label).grid(
            row=row * 2, column=0, padx=22, pady=(2, 3), sticky="w"
        )
        combo = ctk.CTkComboBox(self.left_panel, values=values, height=32)
        combo.grid(row=row * 2 + 1, column=0, padx=22, pady=(0, 8), sticky="ew")
        return combo

    def _on_browse_model(self) -> None:
        path = filedialog.askopenfilename(
            title="Select local Gemma 4 GGUF model",
            filetypes=[("GGUF model files", "*.gguf")],
        )
        if not path:
            return
        self.model_path_entry.delete(0, "end")
        self.model_path_entry.insert(0, path)
        self._refresh_ai_status(show_popup=False)

    def _refresh_ai_status(self, show_popup: bool) -> None:
        status = check_offline_ai_status(self.model_path_entry.get())
        text = (
            f"Model file: {'Found' if status['found'] else 'Missing'}\n"
            f"Active model path: {status['path']}\n"
            f"Runtime: {status['runtime']}\n"
            f"AI mode: {status['ai_mode']}\n"
            f"Internet: {status['internet_status']}"
        )
        self._set_textbox(self.ai_status_box, text)
        if not status["found"]:
            warning = (
                "No local Gemma 4 GGUF model found. Place a .gguf file in models/ "
                "or run download_model.bat."
            )
            self._log(warning)
            if show_popup:
                messagebox.showwarning("Offline AI model missing", warning)
        elif show_popup:
            messagebox.showinfo("Offline AI ready", "Local Gemma 4 GGUF model found.")

    def _show_download_instructions(self) -> None:
        messagebox.showinfo(
            "Download local model",
            (
                "Run download_model.bat from the project/setup folder, or manually place "
                "a compatible .gguf file in this app's models folder. If the model requires "
                "access approval, accept the license on Hugging Face first, then rerun the "
                "script. Normal synthesis uses no internet after the GGUF file is in models/."
            ),
        )

    def _update_future_search_state(self) -> None:
        enabled = bool(self.future_search_switch.get()) if hasattr(self, "future_search_switch") else False
        state = "normal" if enabled else "disabled"
        if hasattr(self, "search_news_button"):
            self.search_news_button.configure(state=state)
        if hasattr(self, "future_warning"):
            self.future_warning.configure(text_color="#D19A66" if enabled else "#6B7280")

    def _on_search_future_news(self) -> None:
        if not self.future_search_switch.get():
            messagebox.showwarning(
                "Future scenario search disabled",
                "Enable online search before searching future project/news scenarios.",
            )
            return

        result = self._validated_inputs()
        if result is None:
            return

        self.search_news_button.configure(state="disabled", text="Searching...")
        self._show_snippets_panel()
        self._set_snippets_text("Searching public web snippets...")
        self._log("Future News Scenario Search enabled by user. Starting public snippet search.")

        thread = threading.Thread(target=self._future_news_worker, args=(result,), daemon=True)
        thread.start()

    def _future_news_worker(self, inputs: GridInputs) -> None:
        try:
            snippets = get_future_scenario_context(inputs.country, inputs.target_year)
            self.after(0, lambda: self._display_snippets(snippets))
            if not snippets:
                self.after(0, lambda: self._log("No future scenario snippets found."))
                scenario = get_future_scenario_anomalies(inputs, [], inputs.local_model_path)
            else:
                self.after(
                    0,
                    lambda: self._log(
                        f"Displayed {len(snippets)} snippets. Analyzing them with local-only logic."
                    ),
                )
                scenario = get_future_scenario_anomalies(inputs, snippets, inputs.local_model_path)

            self.after(
                0,
                lambda: self._on_future_news_success(
                    snippets=snippets,
                    anomalies=scenario.event_anomalies,
                    scenario_label=scenario.scenario_label,
                    local_model_used=scenario.local_model_used,
                    fallback_used=scenario.fallback_used,
                    status_message=scenario.status_message,
                ),
            )
        except Exception as exc:
            error_text = str(exc)
            self.after(0, lambda: self._on_future_news_error(error_text))

    def _on_future_news_success(
        self,
        *,
        snippets: list[WebSnippet],
        anomalies: list[EventAnomaly],
        scenario_label: str,
        local_model_used: bool,
        fallback_used: bool,
        status_message: str,
    ) -> None:
        self.future_snippets = snippets
        self.future_event_anomalies = anomalies
        self.future_scenario_label = scenario_label
        self.web_search_used = True
        self.scenario_local_model_used = local_model_used
        self.scenario_fallback_used = fallback_used
        self.search_news_button.configure(state="normal", text="Search Future Scenario News")
        self._log(status_message)
        self._log(
            f"Future scenario ready: {scenario_label}. "
            f"{len(anomalies)} bounded anomaly/anomalies will be applied on next synthesis."
        )

    def _on_future_news_error(self, error_text: str) -> None:
        self.future_snippets = []
        self.future_event_anomalies = []
        self.future_scenario_label = ""
        self.web_search_used = True
        self.search_news_button.configure(state="normal", text="Search Future Scenario News")
        self._set_snippets_text("Future scenario search failed. Offline synthesis is still available.")
        self._log(f"WARNING: Future News Scenario Search failed gracefully ({error_text}).")

    def _on_synthesize(self) -> None:
        inputs = self._validated_inputs()
        if inputs is None:
            return

        self.current_inputs = inputs
        self.synthesize_button.configure(state="disabled", text="Synthesizing...")
        self._set_export_state(False)
        self._log("Starting offline synthesis worker. No internet calls are made here.")

        thread = threading.Thread(target=self._synthesis_worker, args=(inputs,), daemon=True)
        thread.start()

    def _validated_inputs(self) -> GridInputs | None:
        result = validate_inputs(
            country=self.country_entry.get(),
            target_year=self.year_entry.get(),
            annual_twh=self.annual_entry.get(),
            peak_mw=self.peak_entry.get(),
            climate_profile=self.climate_combo.get(),
            economic_profile=self.economy_combo.get(),
            local_model_path=self.model_path_entry.get(),
            random_seed="",
        )
        if not result.ok or result.inputs is None:
            for error in result.errors:
                self._log(f"ERROR: {error}")
            messagebox.showerror("Invalid inputs", "\n".join(result.errors))
            return None
        for warning in result.warnings:
            self._log(f"WARNING: {warning}")
        if not result.inputs.local_model_path:
            result.inputs.local_model_path = str(default_model_path())
        return result.inputs

    def _synthesis_worker(self, inputs: GridInputs) -> None:
        try:
            parameter_result = get_behavior_parameters(inputs, inputs.local_model_path)
            self._safe_log(parameter_result.status_message)
            params = parameter_result.parameters
            params.event_anomalies = list(self.future_event_anomalies)

            df = synthesize_load_curve(inputs, params)
            local_model_used = parameter_result.local_model_used or self.scenario_local_model_used
            fallback_used = parameter_result.fallback_used or self.scenario_fallback_used
            metadata = build_metadata(
                inputs=inputs,
                df=df,
                parameters=params,
                snippets=self.future_snippets,
                local_model_used=local_model_used,
                fallback_used=fallback_used,
                web_search_used=self.web_search_used,
            )
            self.after(
                0,
                lambda: self._on_synthesis_success(
                    df=df,
                    parameters=params,
                    metadata=metadata,
                ),
            )
        except Exception:
            error_text = traceback.format_exc()
            self.after(0, lambda: self._on_synthesis_error(error_text))

    def _on_synthesis_success(self, *, df, parameters: LLMParameters, metadata: dict) -> None:
        self.current_df = df
        self.current_parameters = parameters
        self.current_metadata = metadata
        self._update_plot()
        self._update_stats()
        self._set_export_state(True)
        self.synthesize_button.configure(state="normal", text="Synthesize Curve")
        self._refresh_ai_status(show_popup=False)
        self._log("Synthesis complete. CSV and metadata exports are enabled.")

    def _on_synthesis_error(self, error_text: str) -> None:
        self.synthesize_button.configure(state="normal", text="Synthesize Curve")
        self._set_export_state(False)
        self._log("ERROR: Synthesis failed. See details below.")
        self._log(error_text)
        messagebox.showerror("Synthesis failed", "The curve could not be synthesized. See status log.")

    def _set_view(self, view: str) -> None:
        self.current_view = view
        self._update_plot()

    def _update_plot(self) -> None:
        if self.current_df is None or self.current_inputs is None:
            return
        plot_load_curve(
            self.ax,
            self.current_df,
            self.current_inputs.country,
            self.current_inputs.target_year,
            self.current_view,
        )
        self._style_axis()
        self.figure.tight_layout()
        self.canvas.draw()

    def _style_axis(self) -> None:
        self.ax.set_facecolor("#282C34")
        self.ax.tick_params(colors="#D7DAE0")
        self.ax.xaxis.label.set_color("#D7DAE0")
        self.ax.yaxis.label.set_color("#D7DAE0")
        self.ax.title.set_color("#D7DAE0")
        for spine in self.ax.spines.values():
            spine.set_color("#5C6370")

    def _update_stats(self) -> None:
        if self.current_df is None or self.current_inputs is None:
            return
        stats = calculate_statistics(
            self.current_df, self.current_inputs.annual_twh, self.current_inputs.peak_mw
        )
        lines = [
            f"Target annual TWh: {stats['annual_energy_target_twh']:.6f}",
            f"Actual annual TWh: {stats['actual_annual_energy_twh']:.6f}",
            f"Target peak MW: {stats['peak_target_mw']:.3f}",
            f"Actual peak MW: {stats['actual_peak_mw']:.3f}",
            f"Load factor: {stats['load_factor']:.4f}",
            f"Mean load MW: {stats['mean_load_mw']:.3f}",
            f"Min load MW: {stats['min_load_mw']:.3f}",
            f"Weekday average: {stats['weekday_average_mw']:.3f}",
            f"Weekend average: {stats['weekend_average_mw']:.3f}",
        ]
        if self.future_event_anomalies:
            lines.append(f"Future scenario anomalies: {len(self.future_event_anomalies)}")
        self._set_textbox(self.stats_box, "\n".join(lines))

    def _display_snippets(self, snippets: list[WebSnippet]) -> None:
        self._show_snippets_panel()
        if not snippets:
            self._set_snippets_text("No future scenario snippets found.")
            return
        blocks = []
        for i, snippet in enumerate(snippets, start=1):
            blocks.append(f"{i}. {snippet.title}\n{snippet.body}\n{snippet.url}")
        self._set_snippets_text("\n\n".join(blocks))

    def _show_snippets_panel(self) -> None:
        self.snippets_label.grid()
        self.snippets_box.grid()

    def _hide_snippets_panel(self) -> None:
        self.snippets_label.grid_remove()
        self.snippets_box.grid_remove()

    def _on_export_csv(self) -> None:
        if self.current_df is None or self.current_inputs is None:
            messagebox.showwarning("No curve", "Synthesize a curve before exporting.")
            return
        initial = default_csv_filename(self.current_inputs.country, self.current_inputs.target_year)
        path = filedialog.asksaveasfilename(
            title="Export PyPSA CSV",
            defaultextension=".csv",
            initialfile=initial,
            initialdir=str(get_outputs_dir()),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            export_pypsa_csv(self.current_df, path)
            self._log(f"CSV exported: {path}")
        except Exception as exc:
            self._log(f"ERROR: CSV export failed ({exc}).")
            messagebox.showerror("Export failed", str(exc))

    def _on_export_metadata(self) -> None:
        if self.current_metadata is None or self.current_inputs is None:
            messagebox.showwarning("No metadata", "Synthesize a curve before exporting metadata.")
            return
        initial = default_metadata_filename(self.current_inputs.country, self.current_inputs.target_year)
        path = filedialog.asksaveasfilename(
            title="Export Metadata JSON",
            defaultextension=".json",
            initialfile=initial,
            initialdir=str(get_outputs_dir()),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            export_metadata_json(self.current_metadata, path)
            self._log(f"Metadata exported: {path}")
        except Exception as exc:
            self._log(f"ERROR: Metadata export failed ({exc}).")
            messagebox.showerror("Export failed", str(exc))

    def _on_clear(self) -> None:
        self.current_df = None
        self.current_parameters = None
        self.current_metadata = None
        self.future_snippets = []
        self.future_event_anomalies = []
        self.future_scenario_label = ""
        self.web_search_used = False
        self.scenario_local_model_used = False
        self.scenario_fallback_used = False
        self._set_export_state(False)
        self.ax.clear()
        self._style_axis()
        self.ax.set_title("No curve synthesized yet")
        self.ax.set_xlabel("Snapshot")
        self.ax.set_ylabel("Load (MW)")
        self.canvas.draw()
        self._set_textbox(self.stats_box, "Synthesize a curve to see statistics.")
        self._set_snippets_text("No future scenario search used.")
        self._hide_snippets_panel()
        self._clear_log()
        self._log("Cleared current curve, future scenario context, and outputs.")

    def _set_export_state(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.export_csv_button.configure(state=state)
        self.export_json_button.configure(state=state)

    def _set_snippets_text(self, text: str) -> None:
        self._set_textbox(self.snippets_box, text)

    def _set_textbox(self, textbox: ctk.CTkTextbox, text: str) -> None:
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("1.0", text)
        textbox.configure(state="disabled")

    def _log(self, text: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{text}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _safe_log(self, text: str) -> None:
        self.after(0, lambda: self._log(text))

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")


def main() -> None:
    app = GridGemmaApp()
    app.mainloop()
