# Indicateurs (Indicators)

Indicators are not a separate data.gouv.fr object type: they are regular **datasets** that opt in via a tag and belong to a specific organization.

## Selection

Configured in `configs/ecospheres/config.yaml` under `pages.indicators` of https://github.com/opendatateam/udata-front-kit/:

```yaml
indicators:
  object_type: datasets
  universe_query:
    tag: ecospheres-indicateurs
    organization: 67884b4da4fca9c97bbef479
  filter_prefix: ecospheres-indicateurs
```

- `object_type: datasets` — the indicators list is a filtered dataset search
- `universe_query`: only datasets tagged `ecospheres-indicateurs` **and** belonging to organization `67884b4da4fca9c97bbef479` are returned.
- `filter_prefix: ecospheres-indicateurs` is reused to:
  - detect a single dataset as an indicator client-side (`dataset.tags.includes(filter_prefix)`),
  - namespace the faceted filter tags (e.g. `secteur`), built as `${filter_prefix}-${filterId}-${valueId}` (see details below).
- Additional facets (`secteur`, `date de mise à jour`, etc.) are plain data.gouv.fr tags following that `ecospheres-indicateurs-<filter>-<value>` convention, configured under `pages.indicators.filters` in the same YAML.

### Tag format for filters: `secteur` example

See https://github.com/opendatateam/udata-front-kit/blob/main/configs/ecospheres/config.yaml > `pages.indicators.filters`

```yaml
- id: secteur
  ...
  use_filter_prefix: true
  values:
    - id: agriculture-forets-sols
      name: Agriculture, Forêts et Sols
    - id: alimentation
      name: Alimentation
    - id: batiment
      name: Bâtiment
    - id: dechets
      name: Déchets
  ...
```

For a dataset to appear under a given "Secteur" facet value, the dataset producer must add the corresponding tag `ecospheres-indicateurs-secteur-<value.id>` to the dataset, i.e. `${filter_prefix}-${filter.id}-${value.id}`. 

For "Agriculture, Forêts et Sols" that tag is `ecospheres-indicateurs-secteur-agriculture-forets-sols`. 

A dataset can carry several `ecospheres-indicateurs-secteur-*` tags if it spans multiple sectors, in addition to the base `ecospheres-indicateurs` tag required for it to be picked up as an indicator at all (see `universe_query` above).

## Native data.gouv.fr metadata used

Standard dataset (`DatasetV2`) fields, displayed as-is:

| Field | Used for |
|---|---|
| `title`, `slug`, `id` | Card/detail titles, routing, identifier display |
| `description` | Detail page body, card excerpt |
| `tags` | Indicator detection + faceted filters (see above), keyword list |
| `spatial.zones` | "Couverture géographique" |
| `temporal_coverage` | "Couverture temporelle" |
| `created_at`, `last_update` | "Date de création" / "Date de mise à jour" |
| `frequency` | "Fréquence de mise à jour" |
| `license` | Licence badge |
| `organization` | Sidebar / source attribution |
| resources (`main` group) | "Fichiers" tab, and viz data source (see below) |
| `extras` (generic) | Rendered in a raw "Extras" accordion for debugging |

## Custom metadata (extras)

### Dataset extras — `ecospheres-indicateurs`

Schema: [`extras_schema.json`](https://github.com/abulte/ecospheres-indicators-dashboard/blob/main/extras_schema.json)

| Key | Type | Required | Used for |
|---|---|---|---|
| `unite` | string | ✅ | Unit label (info panel, one-year value) |
| `mailles_geographiques` | string[] | ✅ | List of geo levels the indicator covers ("Mailles") |
| `axes` | object (`{ [axis]: string[] }`) | ✅ | Declares breakdown axes at dataset level |
| `calcul.responsable` / `calcul.methode` | string | ✅ | "Informations calcul" section |
| `sources[]` (`nom`, `url`, `description`, `producteur`, `distributeur`, `plage_temporelle.start/end`) | array | ✅ | "Sources" tab |
| `enable_visualization` | boolean | ✅ | Shows/hides the "Prévisualisation" tab and chart |
| `summable` | boolean | optional | Whether axis values can be summed/grouped in the chart |
| `y_start_at_zero` | boolean | optional | Chart y-axis behavior |
| `ignore_format_big_number` | boolean | optional | Skip k/M/Md number formatting |
| `next_expected_update_quarter` | string | optional | "Prochaine mise à jour attendue" |

### Resource extras — `ecospheres-indicateurs`

Schema: [`resource_extras_schema.json`](https://github.com/abulte/ecospheres-indicators-dashboard/blob/main/resource_extras_schema.json)

Applied per-resource, only on resources in the dataset's `main` resource group; a resource without this extra is ignored by the visualization.

| Key | Type | Required | Used for |
|---|---|---|---|
| `maille` | string (`fr`\|`region`\|`departement`\|`epci` in this app) | ✅ | Selects which resource backs a given geo-level in the chart |
| `value-column` | string | ✅ | Column in the resource's tabular data holding the measured value |
| `axes` | object (`{ [axis]: string[] }`) | ✅ | Declares which columns/values are selectable as chart breakdown axes for this resource |

Note: the schema does not constrain `maille` to an enum; the frontend narrows it to `fr | region | departement | epci` and maps non-`fr` values to fixed geocode columns (`geocode_region`, `geocode_departement`, `geocode_epci`) plus a fixed `date_mesure` year column — those column names are hardcoded conventions, not part of the extras schema.

## Data flow for visualization

1. Dataset extras `enable_visualization` gates the "Prévisualisation" tab.
2. Among the dataset's `main` group resources, only those carrying resource extras `ecospheres-indicateurs.maille` are candidates.
3. Selecting a mesh (`fr`/`region`/`departement`/`epci`) picks the matching resource; selecting a territory (for non-`fr` meshes) filters rows via the Tabular API using the fixed geocode column for that mesh.
4. Rows are read from `${tabularApiUrl}/api/resources/{resource.id}/data/`, using `value-column` for the Y value and `axes` for breakdown/grouping.

## Monitoring dashboard

A monitoring dashboard is deployed at [indicators-dashboard.sandbox.data.developpement-durable.gouv.fr](https://indicators-dashboard.sandbox.data.developpement-durable.gouv.fr). It crawls indicator datasets on `demo.data.gouv.fr` and `www.data.gouv.fr` and lets the team check, for each one, that its custom metadata (extras) validates against the expected schemas and that its resource files are correctly "APIfied" (reachable and CORS-enabled on the Tabular API) — catching publication issues before they reach the visualization layer.

Github source: https://github.com/abulte/ecospheres-indicators-dashboard