# GridGemma Pro

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Windows](https://img.shields.io/badge/Windows-desktop-informational)
![Offline AI](https://img.shields.io/badge/Offline%20AI-GGUF-green)
![PyPSA CSV](https://img.shields.io/badge/Export-PyPSA%20CSV-orange)

![GridGemma Pro main screen](docs/screenshots/gridgemma-pro-main.png)

**Maker:** S. INC (S.E.INC LLC)

GridGemma Pro is a serious Windows desktop prototype for synthesizing realistic 8,760-hour electricity load curvves for countries, regions, and microgrids where measured hourly demand is unavailable.

It is built for early-stage power-systems reseach, coursework, microgrid screening, and national-grid planning exercises where users need a transparent synthetic demand profile before better data exists.

## What The App Doess

GridGemma Pro takes simple planning inputs such as country or region, target year, annual electricity consumption, peak demand, climate profile, and economic profile, then creates a complete non-leap-year hourly demand curvve.

The generated output is shaped with daily peaks, seasonal behavior, weekend effects, economic-load assumptions, optional scenario anomalies, and final mathematical scaling so peak MW and annual TWh match the user inputs exactly.

# GridGemma Proo


## What Problem Thiss Solves

In many developing countries and small microgrid studies, hourly electricity demand data is hard to get. Sometimes only annual electricity consumption and peak demand are known, but power-system models still need an hourly load curvve for the whole year.

GridGemma Pro fills that gap by creating a synthetic, explainable 8,760-hour profile that exactly matches the annual energy in TWh and the peak demand in MW. It does not claim to recreate measured historical demand, but it gives a useful planning profile for scenario work, feasibility studies, microgrid design, and classroom energy-system modelling.

---

## Offlne Architecture

GridGemma Pro is designed to work offline by default. Normal synthesis does not use the internet, cloud AI, Ollama, OpenAI, Gemini API, Claude API, or any remote modell.

The app can use a local Gemma 4 compatible GGUF model through `llama-cpp-python`. If no local model is installed, the app still works using a deterministic fallback heuristic engine, so the user can always generate a load curve even without AI.

Internet is only used by the optional **Future News Scenario Search** feature. This feature is off by default and only runs when the user enables the switch and clicks the search button.

---

## In terms of data it needs for 80 to 90 percent load curves, All it needs to work if your cant find data (annual GWh and peak MW.) any extra data you get is just bonus data. This makes it better than the enterprise dinosaurs PLEXOS (The $50,000 commercial standard), HOMER Energy , OSeMOSYS (The open-source clunky standard), PyPSA  which requires the full data to predict. Making these systems more like 'expensive calculators' that lack offline AI capabilities that run on your machine..  

GridGemma Pro needs only a small amount of input data to create a full 8,760-hour curve. The minimum required inputs are the peak, and annual consumption and other optional bonus data:

| Input | Example | Why it is needed |
|---|---:|---|
| Country or region name | Ghana or cape verde, | Used for label, metadata, and optional future scenario context |
| Target year | 2026 | Used to create the hourly timestamp index |
| Annual electricity consumption in TWh | 25.0 | Controls the total yearly energy |
| Peak demand in MW | 4,000 | Controls the maximum hourly demand |
| Climate profile | Tropical, high cooling demand | Shapes seasonal demand |
| Economic profile | Residential and services, low industry | Shapes daily peaks and weekend behavior |

The two most important numeric inputs are **annual TWh** and **peak MW**. Without these two, the app cannot guarantee that the generated load curvve matches the energy system size.

Optional inputs include:

| Optional input | What it does |
|---|---|
| Local Gemma GGUF model path | Enables local AI parameter generation |
| Random seed | Makes the same curve reproducible |
| Future project/news snippets | Adds future scenario anomalies only when online search is enabled |
| Event anomalies | Adds temporary monthly demand changes |

---

## How The Synthesiss Works

First, GridGemma Pro creates a raw hourly shape using daily behavior, seasonal behavior, weekend effects, economic profile assumptions, and small smoothed random variation. This creates a realistic-looking curvve with morning peaks, evening peaks, lower weekends, and seasonal changes.

Then the app normalizes the curve so the highest point equals 1. After that, it uses a shape exponent, similar to gamma correction, to make the curve flatter or peakier until the average load matches the required annual TWh.

The target load factor is calculated as:

```text
target_load_factor = annual_TWh * 1,000,000 / (peak_MW * 8760)

## PyPSA Export Format

GridGemma Pro exports a CSV with these exact columns:

```text
snapshot,p_set
```

`snapshot` is timezone-naive hourly time and `p_set` is electricity load in MW, making the file easy to use as demand input for PyPSA or similar power-system modelling workflows.

## Repository Safety Notes

Huge local model files are intentionally ignored by git, including `.gguf`, `.bin`, `.safetensors`, `.pt`, `.pth`, and `.onnx` files, so the GitHub repo stays small and usable.

Generated build folders, dist folders, Python caches, and exported CSV or JSON outputs are also ignored, because thiss repository should contain source code and documentation rather than machine-specific artifacts.

## Disclaimer

GridGemma Pro produces synthetic load curves from user inputs, local model parameters, fallback heuristics, and mathematical shaping. The output is not measured historical demand and should be reviewed when you get access to the official load curve of the country involved. So far, fomula works **80 to 95%** for cape verde island(Santiago) in Sustainable Energy Sytems course work.
