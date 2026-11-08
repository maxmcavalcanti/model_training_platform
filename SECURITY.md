# Security policy

## Supported versions

Only the `main` branch is supported. There are no releases: production runs what is on `main`.

## Reporting a vulnerability

Please do not open a public issue, discussion or pull request for a suspected vulnerability.

Report it privately through GitHub's private vulnerability reporting: open the
**Security** tab of this repository and click **Report a vulnerability**, or go straight to
https://github.com/maxmcavalcanti/model_training_platform/security/advisories/new.

Include the affected file or commit, the steps to reproduce and the impact you expect.
Do not paste working credentials in the report; if you found a leaked secret, say where it is.

## What to expect

This project has a single maintainer, so responses are best effort:

- acknowledgement within 7 days;
- first assessment (accepted, needs more information, or out of scope) within 14 days;
- a fix or mitigation for accepted reports within 90 days, sooner for critical ones.

Disclosure is coordinated through the GitHub security advisory. There is no bug bounty.

## Scope

In scope:

- code in this repository: ingestion jobs, database migrations and role grants, the jobs
  image (`infra/jobs/Dockerfile`), the compose files, scripts and the GitHub Actions workflows;
- secrets committed to the repository or its history;
- supply-chain issues, such as an action or image not pinned by SHA or digest, or a workflow
  that could leak a token or run untrusted code;
- a database role defined here being able to do more than its documented grants.

Out of scope:

- the services are not exposed to the internet; they are reachable only from a private
  network. Do not try to find or reach the production host. Issues that require existing
  access to that private network or to the host are out of scope, unless they let a role
  do more than it is granted;
- vulnerabilities in upstream projects (PostgreSQL, MLflow, Prefect, Grafana, Tailscale,
  Python packages, base images) without a misconfiguration in this repository; report those
  upstream;
- the separate `models` repository;
- the public data sources (Open-Meteo, ONS) and the data they publish;
- denial of service, rate limiting, social engineering;
- scanner output or missing hardening without a demonstrated impact.
