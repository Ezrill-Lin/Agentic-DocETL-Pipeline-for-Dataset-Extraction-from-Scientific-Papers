# Agentic DocETL Pipeline for Dataset Extraction from Scientific Papers

An agentic pipeline that reads scientific papers (PDF, XML, HTML) and extracts dataset references using a two-phase LLM-powered approach, orchestrated via [DocETL](https://github.com/ucbepic/docetl).

## Architecture

```
Input Papers (PDF / XML / HTML)
          │
          ▼
  ┌──────────────────┐
  │  DocETL Pipeline │  pipeline/pipeline.yaml
  └──────┬───────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────┐
│  RTR   │ │  FDR   │
│ Phase  │ │ Phase  │
└───┬────┘ └───┬────┘
    │          │
    ▼          ▼
  data/output/<paper_id>.json
```

### RTR — Read & Extract
The agent reads each section of the paper sequentially, using GPT-4o to identify and extract every dataset reference on the fly.

### FDR — Follow Data References
For each incomplete reference (missing URL or repository), the agent queries GPT-4o to complete it, then validates every URL for accessibility. Invalid URLs trigger a further repair attempt (up to 3 tries total).

### Loop
RTR → FDR repeats until no new references are found in a cycle (max 3 cycles).

## Extracted Fields

| Field | Description |
|---|---|
| `dataset_identifier` | Name or canonical ID of the dataset |
| `repository` | Hosting platform (Zenodo, GitHub, UCI, Kaggle, HuggingFace, …) |
| `url` | Direct URL to the dataset |
| `description` | One-sentence description |
| `paper_source` | Paper ID this was extracted from |
| `status` | `complete` / `validated` / `incomplete` / `unresolved` / `invalid_url` |

## Setup

### 1. Clone & install dependencies

```bash
git clone <repo-url>
cd Agentic-DocETL-Pipeline-for-Dataset-Extraction-from-Scientific-Papers
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY
```

### 3. Add papers

Copy your PDF, XML, or HTML paper files to `data/input/`.

## Usage

### Run with the Python entry point

```bash
# Process all papers in data/input/
python run_pipeline.py --input data/input/

# Process a single paper
python run_pipeline.py --file path/to/paper.pdf

# Custom output directory
python run_pipeline.py --input data/input/ --output data/output/
```

### Run via DocETL

```bash
docetl run pipeline/pipeline.yaml
```

## Output

Each paper produces `data/output/<paper_id>.json`:

```json
{
  "paper_id": "3f8a1d2c9b4e",
  "paper_title": "Attention Is All You Need",
  "references": [
    {
      "dataset_identifier": "WMT 2014 English-German",
      "repository": "statmt.org",
      "url": "https://www.statmt.org/wmt14/translation-task.html",
      "description": "Machine translation benchmark dataset",
      "paper_source": "3f8a1d2c9b4e",
      "status": "validated"
    }
  ],
  "cycles_run": 1,
  "total_sections": 12
}
```

A `manifest.json` summary is also written to the output directory.

## Project Structure

```
├── src/dataset_extractor/
│   ├── agents/
│   │   ├── prompts.py          # LLM prompts for RTR and FDR
│   │   ├── rtr_agent.py        # Read & Extract agent
│   │   └── fdr_agent.py        # Follow Data References agent
│   ├── docetl_ops/
│   │   └── operations.py       # Custom DocETL operation wrappers
│   ├── parsers/
│   │   └── paper_parser.py     # PDF / XML / HTML parsers
│   ├── config.py               # Environment configuration
│   ├── logging_utils.py        # Structured JSON logging
│   ├── models.py               # Pydantic data models
│   └── url_validator.py        # URL accessibility checker
├── pipeline/
│   └── pipeline.yaml           # DocETL pipeline definition
├── tests/                      # Unit tests
├── data/
│   ├── input/                  # Place papers here
│   └── output/                 # Extracted JSON results
├── logs/                       # JSON log files
├── run_pipeline.py             # CLI entry point
└── requirements.txt
```

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | Required. Your OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model to use |
| `MAX_REPAIR_ATTEMPTS` | `3` | Max FDR repair tries per reference |
| `MAX_RTR_FDR_CYCLES` | `3` | Max RTR→FDR loop cycles |
| `LOG_LEVEL` | `INFO` | Logging level |
