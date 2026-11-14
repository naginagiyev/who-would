# Who Would

A party voting game, deployed to an Azure VM with Terraform, Docker Compose, and GitHub Actions.

**Live:** http://68.210.36.252

A host creates a room, friends join with a 4-letter code, the host asks a "Who would...?" question,
everyone votes for another player, and the host reveals the results. Every push to `main` is tested,
built, and deployed automatically.

## Contents

- [Architecture](#architecture)
- [Why a VM and a containerized PostgreSQL](#why-a-vm-and-a-containerized-postgresql)
- [Repository layout](#repository-layout)
- [Set it up yourself](#set-it-up-yourself)
- [How the pipeline works](#how-the-pipeline-works)
- [How to verify](#how-to-verify)
- [Rollback](#rollback)
- [Run and test locally](#run-and-test-locally)
- [Security](#security)
- [Cost and how to stop or delete](#cost-and-how-to-stop-or-delete)
- [Evidence](#evidence)
- [Known limitations](#known-limitations)

## Architecture

```mermaid
flowchart LR
    dev[Developer] -->|git push to main| gha[GitHub Actions]

    subgraph ci[Job build-test]
        tests[pytest against a PostgreSQL service] --> build[docker build linux/amd64]
    end

    gha --> tests
    build -->|push :commit-sha and :latest| ghcr[(GHCR image registry)]

    subgraph azure[Azure, austriaeast, created by Terraform]
        nsg{{NSG firewall: 80 for all, 22 for 2 IPs}}
        identity[Managed identity who-would-deploy]
        subgraph vm[VM who-would-vm, Ubuntu 24.04 + Docker]
            web[web container: FastAPI on 8000]
            db[(db container: PostgreSQL 17)]
            volume[(named volume db-data)]
        end
    end

    gha -->|job deploy: OIDC login, no password| identity
    identity -->|az vm run-command| vm
    ghcr -->|docker compose pull web| web
    players[Players] -->|HTTP port 80| nsg --> web
    web -->|db:5432 on a private Docker network| db
    db --> volume
    terraform[Terraform in infra/] -.->|terraform apply| azure
```

| Part | What it is |
|---|---|
| Web app | Python 3.12, FastAPI, server-rendered Jinja2 pages, psycopg. The room page updates itself every 2 seconds. |
| Database | PostgreSQL 17 in a container. Data lives in the named volume `db-data`, so it survives container restarts and redeploys. The port is not published. |
| Runtime | Docker Compose on one Azure VM (`Standard_B2ats_v2`). |
| Infrastructure as Code | Terraform (`azurerm` provider): resource group, VNet, subnet, NSG, static public IP, NIC, VM with cloud-init, and the deploy identity. |
| CI/CD | GitHub Actions: test, build, push to GHCR, deploy with `az vm run-command`, verify `/health`. |

**Configuration.** The app reads only one setting: `DATABASE_URL`. Compose builds it from
`POSTGRES_PASSWORD`, which is in a `.env` file on each machine and never in Git. The tables are
created by the app at startup from `app/schema.sql`.

## Why a VM and a containerized PostgreSQL

- **VM:** cheap (about $14 a month in total), simple to explain, and it shows what you are
  responsible for yourself (OS, Docker, firewall rules). App Service plus a managed database would
  cost more and hide most of that.
- **PostgreSQL in a container with a named volume:** the database stays on a private Docker network
  that only the app can reach, and the data survives every deploy. A managed database would add
  cost and a second network path to secure.
- **Trade-off:** one VM means no redundancy and a few seconds of downtime per deploy, and you must
  patch the OS. See [Known limitations](#known-limitations).

## Repository layout

```
app/                    FastAPI app, schema.sql, Jinja2 templates, tests/
infra/                  Terraform: main.tf, variables.tf, outputs.tf, cloud-init.yaml
.github/workflows/      deploy.yml: the CI/CD pipeline
evidence/               Proof of provisioning and a pipeline run
Dockerfile              Image for the web app (built with uv)
compose.yaml            web + db services and the db-data volume
pyproject.toml, uv.lock Python dependencies (exact versions locked)
paths.py                File paths used by the app
```

## Set it up yourself

### 1. One-time prerequisites

- An Azure subscription where you are **Owner** (Terraform creates a role assignment), and the
  [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli). Log in:
  ```
  az login
  az account show
  ```
- [Terraform](https://developer.hashicorp.com/terraform/install) 1.9 or newer.
- A fork or copy of this repository on GitHub. Keep it **public**, so the GHCR image is public and
  the VM can pull it without a login.
- An SSH key for your own admin access:
  ```
  ssh-keygen -t ed25519 -f ~/.ssh/who-would
  ```
- Your repository's numeric owner and repo IDs. GitHub puts them into the OIDC token:
  ```
  curl https://api.github.com/repos/OWNER/REPO
  ```
  Use `"id"` at the top (repo ID) and `"owner": {"id": ...}` (owner ID).

If you use your own fork, change these names in the code:

| File | What to change |
|---|---|
| `compose.yaml` | `image: ghcr.io/naginagiyev/who-would:...` to `ghcr.io/OWNER/REPO:...` (lowercase) |
| `.github/workflows/deploy.yml` | `APP_URL` (after step 2), and `RESOURCE_GROUP` / `VM_NAME` if you rename them |

### 2. Provision the infrastructure (one command)

Create `infra/terraform.tfvars` (it is git-ignored):

```hcl
subscription_id = "<your subscription id>"
ssh_source_ips  = ["<your public IP>"]
github_repo     = "<owner>@<owner_id>/<repo>@<repo_id>"
```

Optional variables: `location` (default `austriaeast`), `vm_size` (default `Standard_B2ats_v2`),
`ssh_public_key_path` (default `~/.ssh/who-would.pub`).

Then run:

```
terraform -chdir=infra init
terraform -chdir=infra apply
```

`apply` shows the plan and asks for `yes`. It creates 11 resources: the resource group
`who-would-rg`, the network, the NSG, the static public IP, the NIC, the VM `who-would-vm`, and the
deploy identity with its trust rule and role. On the first boot, cloud-init
(`infra/cloud-init.yaml`) installs Docker and Docker Compose, adds a 2 GB swap file, and creates
`/opt/who-would`.

Read the outputs; you need them in the next steps:

```
terraform -chdir=infra output
```

### 3. One-time VM bootstrap

Log in and wait until cloud-init has finished:

```
ssh -i ~/.ssh/who-would azureuser@<public_ip>
cloud-init status --wait
```

Then, on the VM, clone the repo and create the production `.env` with a random password:

```
git clone https://github.com/OWNER/REPO.git /opt/who-would
cd /opt/who-would
echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)" > .env
chmod 600 .env
```

This password stays only on the VM. PostgreSQL saves it when the volume is first created, so do not
change it later.

### 4. Configure the pipeline

In GitHub: **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `AZURE_CLIENT_ID` | `terraform -chdir=infra output -raw azure_client_id` |
| `AZURE_TENANT_ID` | `terraform -chdir=infra output -raw azure_tenant_id` |
| `AZURE_SUBSCRIPTION_ID` | your subscription ID |

These are IDs, not passwords. There is no SSH key, Azure password, or database password in GitHub.

### 5. Trigger it

Any push to `main` starts the pipeline. The first run builds the image, pushes it to GHCR, and
deploys it.

## How the pipeline works

`.github/workflows/deploy.yml`, trigger: `on: push: branches: [main]`.

| Stage | Job and step | What happens |
|---|---|---|
| **Build and check** | `build-test` | Starts a fresh Ubuntu runner and a throwaway PostgreSQL service container. Installs the exact locked dependencies with `uv sync --frozen` and runs `uv run pytest -v` (4 tests). |
| | | Only if the tests pass: logs in to GHCR with the automatic `GITHUB_TOKEN`, builds the image for `linux/amd64`, and pushes `ghcr.io/OWNER/REPO:<commit-sha>` and `:latest`. |
| **Deploy** | `deploy` (`needs: build-test`) | Gets a GitHub OIDC token and exchanges it for a short Azure login as `who-would-deploy`. That identity is trusted only for `main` of this repo and may only manage this one VM. |
| | | `az vm run-command invoke` runs a script inside the VM (no SSH): `git pull`, then `IMAGE_TAG=<commit-sha> docker compose pull web` and `docker compose up -d`. Only `web` is replaced; `db` and its volume are untouched. |
| | | Checks that the running image contains the commit SHA (run-command itself reports success even when the script fails). |
| **Verify** | `Verify` step | Calls `http://<public_ip>/health` up to 10 times, 5 seconds apart. `/health` runs `SELECT 1`, so it only returns 200 when the app can reach the database. No 200 means a red job. |

A failed test means no image and no deploy. Results and logs are in the **Actions** tab; the step
"Deploy on the VM" shows the VM's own output.

## How to verify

1. Open `http://<public_ip>` (here: http://68.210.36.252), create a room, join it from a second
   tab or phone, ask a question, vote, and reveal.
2. Health check:
   ```
   curl http://68.210.36.252/health
   ```
   Expected: `{"status":"ok"}`
3. **Data survives a redeploy:** with a room open, change something visible (for example the
   heading in `app/templates/base.html`), push to `main`, wait for the green run, and reload the
   room. The new version is live and the room, players, and votes are still there.
4. **Which version is running** (on the VM):
   ```
   docker ps --format '{{.Names}} {{.Image}}'
   ```
   `who-would-web-1` shows `ghcr.io/OWNER/REPO:<sha of the latest commit>`.
5. **The database is not reachable from the internet:**
   ```
   Test-NetConnection 68.210.36.252 -Port 5432    # Windows: TcpTestSucceeded False
   nc -vz -w 5 68.210.36.252 5432                 # Linux/macOS: times out
   ```
   Port 80 answers; port 5432 times out, because the NSG has no rule for it and nothing on the VM
   listens on it (`sudo ss -tlnp` shows only 22 and 80).

## Rollback

Every image is kept in GHCR with its commit SHA.

- **Normal way:** in the **Actions** tab, open the run of the last good commit, hover over the
  `deploy` job, click the re-run icon, and confirm **Re-run jobs**. A re-run uses the same commit
  SHA, so that exact image is deployed again in about a minute, without a rebuild.
- **Emergency way (on the VM):**
  ```
  cd /opt/who-would
  IMAGE_TAG=<full sha of a good commit> docker compose up -d web
  ```

Logs: `docker compose logs web` and `docker compose logs db` on the VM (add `--follow` to watch).

## Run and test locally

Requires Docker and [uv](https://docs.astral.sh/uv/).

```
echo POSTGRES_PASSWORD=devpass > .env
docker compose up -d --build
```

Open http://localhost. `--build` builds the image locally instead of pulling it.

Tests use their own throwaway database, so your local data is not touched:

```
docker run -d --rm --name whowould-test -e POSTGRES_PASSWORD=devpass -p 5432:5432 postgres:17
DATABASE_URL=postgresql://postgres:devpass@localhost:5432/postgres uv run pytest
docker stop whowould-test
```

(On Windows PowerShell, set the variable first: `$env:DATABASE_URL="postgresql://postgres:devpass@localhost:5432/postgres"`.)

## Security

| Port | Who can reach it |
|---|---|
| 80 (HTTP) | Everyone (the app) |
| 22 (SSH) | Only the IPs in `ssh_source_ips`; key login only, password login disabled |
| 5432 (PostgreSQL) | Nobody from outside: no NSG rule, and the port is not published by Compose |
| Deploys | Not through a port: Azure API plus the VM agent (`run-command`) |

| Secret | Where it lives |
|---|---|
| Production database password | Only in `/opt/who-would/.env` on the VM (`chmod 600`) |
| Azure login for deploys | Not stored: OIDC gives a short-lived login per run |
| GHCR push token | Not stored: `GITHUB_TOKEN`, created per run |
| Azure IDs | GitHub Secrets |
| SSH private key, subscription ID, admin IPs | On the admin's laptop only (`~/.ssh`, git-ignored `terraform.tfvars`) |

`.env`, `*.tfstate*`, `*.tfvars`, and `tfplan` are git-ignored. The full Git history was scanned
and contains no secrets. Ubuntu installs security updates automatically (`unattended-upgrades`).

**Who manages what:** Azure manages the hardware, the hypervisor, the network and firewall engine,
and the disk storage. We manage the OS and its updates, Docker, the firewall rules, the database and
its backups, and the app.

## Cost and how to stop or delete

Azure retail prices for `austriaeast` (USD, 730 hours a month):

| Resource | Always on | VM deallocated |
|---|---|---|
| VM `Standard_B2ats_v2` ($0.0108/hour) | $7.88 | $0 |
| OS disk, Standard SSD E4 | about $2.50 | about $2.50 |
| Static public IP ($0.005/hour) | $3.65 | $3.65 |
| VNet, NSG, NIC, identity, role, GHCR, GitHub Actions (public repo) | free | free |
| **Total per month** | **about $14** | **about $6** |

Stop the VM (keeps disk, data, and IP; no VM charge):

```
az vm deallocate -g who-would-rg -n who-would-vm
```

Start it again (same IP; Docker and the containers start by themselves):

```
az vm start -g who-would-rg -n who-would-vm
```

Do not use `az vm stop` to save money: Azure keeps charging for a stopped but not deallocated VM.

Delete everything, including all data (cost goes to $0):

```
terraform -chdir=infra destroy
```

## Evidence

| File | What it shows |
|---|---|
| [evidence/terraform-apply.txt](evidence/terraform-apply.txt) | The first `terraform apply`: 8 resources created, public IP output (subscription ID removed) |
| [evidence/azure-resources.png](evidence/azure-resources.png) | The resource group in the Azure portal |
| [evidence/pipeline-run.png](evidence/pipeline-run.png) | A green pipeline run with both jobs, `build-test` and `deploy` |

The deploy identity (3 more resources) was added later with a second `terraform apply`. The
Actions tab shows every pipeline run, including a deliberately failed one: commit `7bd5ee8` broke
`/health`, the tests failed, and no image was published for it.

## Known limitations

- One VM, one disk, no backups: if the disk is lost, the data is lost.
- A few seconds of downtime on each deploy, because there is only one `web` container.
- Plain HTTP, no TLS certificate.
- A failed verify does not roll back automatically; re-run the last good deploy.
- Changing `infra/cloud-init.yaml` makes Terraform recreate the VM, which deletes the data.
- Players are identified by `?player_id=` in the URL, so a player could act as another one.
