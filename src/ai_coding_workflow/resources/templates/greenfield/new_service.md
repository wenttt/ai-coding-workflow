---
jira_key: "{{ jira_key }}"
mode: greenfield
ticket_type: epic
risk_level: high
proposed_stack:
  language: "{{ e.g. Python 3.12 }}"
  framework: "{{ e.g. FastAPI }}"
  database: "{{ }}"
  deployment: "{{ }}"
ac:
  - "{{ ac_1 }}"
affected_modules: []
service_name: "{{ name }}"
service_type: "http | grpc | event-consumer | batch"
---

# Greenfield Service Design: {{ ticket.summary }}

> Jira: [{{ jira_key }}]({{ ticket.url }})
> Type: New Service (greenfield, separately deployed) — full microservice

## Service summary

One paragraph: what does this service do, how do clients invoke it, what does it own.

## Why a service (not a library / module)

Like new_module, but stronger threshold. State the case:
- Independent deployment cadence: this changes on a different schedule than other services
- Operational ownership: a different team owns SLO
- Tech requirements: different runtime / scaling shape than other services

## API surface

| Method | Path | Purpose | Auth |
|---|---|---|---|
| POST | /v1/foo | ... | ... |

Or for non-HTTP services: events consumed, events produced, batch inputs/outputs.

## Data model

Owned tables / collections. Schemas. Relationships to other services' data.

## Tech stack decision

(Same matrix as new_project.md — language / framework / DB / deployment / CI.)

## Deployment shape

- Runtime: containers / serverless / VMs
- Scale: estimated QPS, memory, CPU
- Dependencies: which other services / DBs / queues

## Observability

- Logs: format, where shipped
- Metrics: which dashboards to wire up
- Alerts: SLO targets, on-call

## Phasing

Sub-tasks that get this service from "doesn't exist" to "in production".

## Acceptance criteria (service-level)

## Open questions
