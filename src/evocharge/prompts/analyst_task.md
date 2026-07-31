# Analyst Agent — Task

Analyze the following validated Milestone-5 diagnostic evidence.

## Timing note
{{timing_note}}

## Diagnostic identity
- diagnostic_id: {{diagnostic_id}}
- diagnostic_hash: {{diagnostic_hash}}

## Dataset summary
```json
{{dataset_summary}}
```

## Objective summary
```json
{{objective_summary}}
```

## Observed metrics
```json
{{observed_metrics}}
```

## Metric availability
```json
{{metric_availability}}
```

## Failure taxonomy (allowed labels)
```json
{{failure_taxonomy}}
```

## Representative evidence (bounded)
```json
{{representative_evidence}}
```

Produce an AnalystReport JSON object. Every ranked mechanism must include at least one EvidenceReference whose `path` resolves in the observed metrics / representative evidence, and whose `observed_value` matches the artifact when a value is stated.
