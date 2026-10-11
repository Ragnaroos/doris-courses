# Observability with Apache Doris

This directory contains the DOG observability labs and a shared Python runtime
for notebook cells. The runtime follows the same learner-facing pattern as the
real-time analytics course.

## Set up the Python environment

Run these commands from this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Start JupyterLab from the same directory:

```bash
.venv/bin/jupyter lab
```

Every executable notebook finds this course root, imports the stable `DorisLab`
facade (the observability-specific class is also exported as
`ObservabilityLab`), and creates a `lab` object. Once that cell has run, a learner
can execute shell or Doris commands directly from later cells:

```python
lab.shell("docker ps", title="Running containers")
lab.sql("SELECT VERSION() AS doris_version", title="Doris version")
lab.execute("CREATE DATABASE IF NOT EXISTS otel")
```

Module 1 prepares the persistent DOG stack. It clones the upstream stack into
the ignored `.runtime/` directory, mounts the Doris log directories, and starts
Doris, Grafana, and the OpenTelemetry Collector. Module 2 then starts dedicated
collectors for logs, metrics, and traces.

Docker state is kept outside the course files. Re-running an environment cell
reuses existing containers and data instead of replacing them.

## Interactive quizzes

Each module includes a six-question, single-choice knowledge check. The
quizzes use the shared `doris_course.quiz` interface and do not require a
running Docker environment or external services.

Level 1:

- Module 1: [Notebook](level1/module01-observability-introduction/quiz1_observability_foundations.ipynb) · [Question YAML](level1/module01-observability-introduction/quiz1_observability_foundations.yaml)
- Module 2: [Notebook](level1/module02-data-ingest/quiz2_ingesting_observability_data.ipynb) · [Question YAML](level1/module02-data-ingest/quiz2_ingesting_observability_data.yaml)
- Module 3: [Notebook](level1/module03-data-visualization/quiz3_observability_visualization.ipynb) · [Question YAML](level1/module03-data-visualization/quiz3_observability_visualization.yaml)

Level 2:

- Module 1: [Notebook](level2/module01-table-model/quiz1_observability_table_models.ipynb) · [Question YAML](level2/module01-table-model/quiz1_observability_table_models.yaml)
- Module 2: [Notebook](level2/module02-partition-bucket/quiz2_partition_and_bucket_choices.ipynb) · [Question YAML](level2/module02-partition-bucket/quiz2_partition_and_bucket_choices.yaml)
- Module 3: [Notebook](level2/module03-property-mv-index/quiz3_properties_mv_and_indexes.ipynb) · [Question YAML](level2/module03-property-mv-index/quiz3_properties_mv_and_indexes.yaml)
- Module 4: [Notebook](level2/module04-data-analysis-litefuse/quiz4_analysis_and_litefuse.ipynb) · [Question YAML](level2/module04-data-analysis-litefuse/quiz4_analysis_and_litefuse.yaml)
- Module 5: [Notebook](level2/module05-alarm/quiz5_alerting_rules.ipynb) · [Question YAML](level2/module05-alarm/quiz5_alerting_rules.yaml)
