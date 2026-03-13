---
title: "How I built this blog: Docker, Azure, GitHub Actions and Cloudflare from scratch"
date: 2026-03-13
excerpt: "A complete technical walkthrough of every step required to build a static blog with automated deployment. No shortcuts, errors included."
---

This post documents, step by step, how the infrastructure behind this blog was built. This is not a simplified tutorial: it includes every command executed, every error encountered, and how each was resolved.

The goal: a static blog where publishing is as easy as writing a markdown file and running `git push`. Everything between "push" and "live" is automated.

## Stack overview

- Python for a build script that converts markdown to HTML
- Docker to package the site in a container with Nginx
- Azure Container Registry to store Docker images
- Azure Container Apps to serve the site
- GitHub Actions to automate the build and deployment
- Cloudflare for DNS and SSL certificate
- Custom domain: alsurdelafrontera.org

## Project structure

```
al-sur-de-la-frontera/
├── posts/                     ← markdown files for each post
│   ├── 2026-03-12-por-que-empece-este-blog.md
│   ├── 2026-03-08-notas-sobre-vivir-despacio.md
│   └── 2026-03-01-lo-que-no-se-puede-medir.md
├── templates/
│   └── base.html              ← HTML template with placeholder
├── static/
│   └── style.css              ← site styles
├── build.py                   ← script that generates the final HTML
├── requirements.txt           ← Python dependencies
├── Dockerfile                 ← two-stage Docker image
├── nginx.conf                 ← web server configuration
├── .dockerignore              ← Docker build exclusions
└── .github/
    └── workflows/
        └── deploy.yml         ← CI/CD pipeline
```

The key architectural decision is the separation between **build time** and **serve time**. The Python script, the markdown files, and the template only exist during the build. The final Docker container only contains Nginx, the generated `index.html`, and the CSS file. Visitors never interact with the build tools.

## Step 1: The markdown-to-HTML build system

Each post is a `.md` file with a metadata block called frontmatter at the top:

```markdown
---
title: "Post title"
date: 2026-03-12
excerpt: "Short description."
---

Markdown content here...
```

The triple dashes (`---`) delimit the frontmatter, which is YAML. Everything after the second `---` is the post body in markdown.

The HTML template (`templates/base.html`) contains the blog's layout with a placeholder `__POSTS_DATA__` where the build script injects the post data as a JavaScript JSON array. The CSS is extracted into a separate file (`static/style.css`) for independent browser caching.

The build script (`build.py`) executes the following:

1. Scans the `posts/` folder for `.md` files
2. For each file, separates the frontmatter (YAML) from the body (markdown)
3. Converts the markdown body to HTML using the `markdown` library
4. Formats dates in Spanish (e.g., "12 mar 2026")
5. Sorts posts by date, newest first
6. Serializes everything as JSON and injects it into the template
7. Outputs the final `output/index.html`

The only dependencies are `markdown` and `pyyaml`, listed in `requirements.txt`.

## Step 2: Docker and Nginx

`nginx.conf` configures Nginx to serve static files on port 80, with a 7-day cache for CSS files. Minimal configuration — sufficient for static content.

The Dockerfile uses two stages (multi-stage build):

- **Stage 1 (builder):** Uses a Python 3.12 slim image, installs dependencies, copies source files, and runs `build.py` to generate `index.html`.
- **Stage 2 (server):** Uses an Nginx Alpine image (~7MB), copies ONLY the generated HTML and CSS from stage 1. Python, the build script, and the markdown files are discarded.

Result: a ~40MB image containing only Nginx and static files.

`.dockerignore` excludes unnecessary files from the build context: `.git`, `README.md`, the `output/` folder, editor files, etc.

**Local test on Windows:**

```
docker build -t alsurdelafrontera:test .
docker run -p 8080:80 alsurdelafrontera:test
```

The build completed in 7.7 seconds across all 22 steps. The site was accessible at `http://localhost:8080`.

## Step 3: Azure — creating the infrastructure

### Installing Azure CLI

```
winget install -e --id Microsoft.AzureCLI
```

The terminal must be restarted after installation for the `az` command to be recognized.

### Logging into Azure

The first attempt with `az login` failed with a Windows Account Manager (WAM) error:

```
Unexpected exception while waiting for accounts control to finish:
'A specified logon session does not exist. It may already have been terminated.'
```

`az logout` followed by `az login` produced the same error. The solution was to bypass the WAM broker using the device code flow:

```
az login --use-device-code
```

This displays a code and a URL. Authentication is completed through the browser.

### Creating the Resource Group

A Resource Group is a logical container in Azure that groups related resources.

```
az group create --name rg-alsurdelafrontera --location spaincentral
```

### Creating the Container Registry

```
az acr create --name alsurdelafrontera --resource-group rg-alsurdelafrontera --sku Basic --admin-enabled true
```

This failed with a `MissingSubscriptionRegistration` error: the subscription was not registered to use the `Microsoft.ContainerRegistry` namespace. This is expected behavior for new Azure subscriptions.

The fix — registering the required providers:

```
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
```

Registration status can be verified with:

```
az provider show --namespace Microsoft.ContainerRegistry --query "registrationState"
```

Once registered, the registry creation command succeeded.

**Parameter breakdown:**

- `--name alsurdelafrontera` — registry name, becomes the URL `alsurdelafrontera.azurecr.io`
- `--sku Basic` — lowest tier (~5-7€/month), includes 10GB storage
- `--admin-enabled true` — enables username/password authentication for Docker

### Pushing the Docker image to Azure

```
az acr login --name alsurdelafrontera
docker tag alsurdelafrontera:test alsurdelafrontera.azurecr.io/blog:v1
docker push alsurdelafrontera.azurecr.io/blog:v1
```

### Deploying to Container Apps

```
az containerapp up --name blog-alsurdelafrontera --resource-group rg-alsurdelafrontera --location spaincentral --image alsurdelafrontera.azurecr.io/blog:v1 --target-port 80 --ingress external
```

This command created three resources automatically:

- A Container Apps environment (`blog-alsurdelafrontera-env`)
- A Log Analytics workspace
- The container app (`blog-alsurdelafrontera`)

Output: a public URL at `https://blog-alsurdelafrontera.salmonsky-5b6d2ef3.spaincentral.azurecontainerapps.io`

### Resources and cost breakdown

`az resource list --resource-group rg-alsurdelafrontera --output table` showed four resources:

| Resource | Type | Monthly cost |
|----------|------|-------------|
| alsurdelafrontera | Container Registry (Basic) | ~€5-7 |
| workspace-rgalsurdelafronteraKImU | Log Analytics workspace | €0 (free tier, 5GB/month) |
| blog-alsurdelafrontera-env | Container Apps environment | €0 (Consumption plan) |
| blog-alsurdelafrontera | Container App | ~€0-1 (free tier covers it) |

Total estimated cost: ~€5-8/month, almost entirely from the Container Registry. The Container App has free monthly grants: 180,000 vCPU-seconds, 360,000 GiB-seconds, and 2 million requests. A low-traffic static site stays well within these limits.

## Step 4: GitHub Actions — automating the deployment

### Repository setup

Git was already installed (via Git Bash). Identity configuration:

```
git config --global user.name "Name"
git config --global user.email "marccantavella@users.noreply.github.com"
```

A public repository was created on GitHub (`al-sur-de-la-frontera`) with no initial files. Local initialization:

```
git init
git add .
git commit -m "Initial commit: blog with build script and Dockerfile"
git branch -M main
git remote add origin https://github.com/marccantavella/al-sur-de-la-frontera.git
git push -u origin main
```

The push failed with error `GH007: Your push would publish a private email address.` GitHub's email privacy protection blocked the push. Fix: use GitHub's no-reply address.

```
git config --global user.email "marccantavella@users.noreply.github.com"
git commit --amend --reset-author --no-edit
git push -u origin main
```

### GitHub Secrets

GitHub Actions requires credentials to interact with Azure. Container Registry credentials were obtained with:

```
az acr credential show --name alsurdelafrontera --output table
```

A service principal was created for Azure authentication:

```
az ad sp create-for-rbac --name "github-deploy-blog" --role contributor --scopes /subscriptions/MY-SUBSCRIPTION-ID/resourceGroups/rg-alsurdelafrontera --sdk-auth
```

Four secrets were added in GitHub (Settings → Secrets and variables → Actions):

- `ACR_USERNAME` — Container Registry username
- `ACR_PASSWORD` — Container Registry password (first of two)
- `ACR_LOGIN_SERVER` — `alsurdelafrontera.azurecr.io`
- `AZURE_CREDENTIALS` — full JSON blob from the service principal

### The workflow (deploy.yml)

`.github/workflows/deploy.yml` contains six steps:

1. **Checkout code** — pulls the latest code from the repository
2. **Log in to ACR** — authenticates Docker with the Container Registry
3. **Build Docker image** — runs `docker build`, tags with `latest` and commit SHA
4. **Push to ACR** — uploads the image to the registry
5. **Azure Login** — authenticates with Azure using the service principal
6. **Deploy to Container Apps** — runs `az containerapp update` with the new image

### First run: failure and fix

The first pipeline run failed. Steps 1-4 succeeded. Step 5 ("Deploy to Container Apps") returned:

```
ERROR: Please run 'az login' to setup account.
```

Root cause: the workflow was missing an explicit Azure login step. The `azure/cli@v2` action does not automatically authenticate — `azure/login@v2` must be called first with the `AZURE_CREDENTIALS` secret.

After adding the login step, the second run completed successfully in 1 minute 11 seconds.

### End-to-end test

A new post was created and pushed. The pipeline ran successfully (green), but the post did not appear. Investigation revealed that Windows had saved the file as `.md.txt` (double extension). The build script only processes `.md` files.

Fix:

```
Rename-Item "2026-03-13-mi-primer-deploy.md.txt" "2026-03-13-mi-primer-deploy.md"
git add .
git commit -m "Fix: rename post file from .md.txt to .md"
git push
```

The post appeared after the pipeline completed.

**Note:** When saving files in Windows text editors, always set "Save as type" to "All Files (*.*)" to prevent automatic `.txt` extension.

## Step 5: Custom domain with Cloudflare

### DNS records

Two records were added in Cloudflare's DNS dashboard:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| TXT | asuid | (Azure's domain verification ID) | DNS only |
| CNAME | @ | blog-alsurdelafrontera.salmonsky-5b6d2ef3.spaincentral.azurecontainerapps.io | DNS only |

The verification ID was obtained with:

```
az containerapp show --name blog-alsurdelafrontera --resource-group rg-alsurdelafrontera --query "properties.customDomainVerificationId" --output tsv
```

Both records were set to **DNS only** (gray cloud) for initial setup.

### Adding the hostname to Azure

```
az containerapp hostname add --name blog-alsurdelafrontera --resource-group rg-alsurdelafrontera --hostname alsurdelafrontera.org
```

### SSL certificate binding

CNAME validation failed for the root domain:

```
az containerapp hostname bind ... --validation-method CNAME
(InvalidValidationMethod) Invalid validation method for domain 'alsurdelafrontera.org'.
Supported validation method(s) for the domain are: HTTP, TXT.
```

TXT validation was used instead:

```
az containerapp hostname bind --name blog-alsurdelafrontera --resource-group rg-alsurdelafrontera --hostname alsurdelafrontera.org --environment blog-alsurdelafrontera-env --validation-method TXT
```

Azure provided a TXT token to add in Cloudflare:

| Type | Name | Content |
|------|------|---------|
| TXT | _dnsauth | (token provided by Azure) |

Certificate provisioning takes up to 20 minutes. Once complete, the site was accessible at `https://alsurdelafrontera.org`.

## Summary

The publishing workflow:

1. Create a new `.md` file in `posts/`
2. `git add . → git commit → git push`
3. Wait ~2 minutes
4. Post is live at alsurdelafrontera.org

Everything between "push" and "live" is automated: GitHub Actions detects the push, builds the Docker image (which runs the Python script inside), pushes it to Azure Container Registry, and updates the Container App. No manual intervention, no servers to manage.

Total monthly cost: ~€5-8, almost entirely from the Container Registry.

Technologies covered: Docker multi-stage builds, Nginx configuration, Azure CLI, resource providers and subscription registration, Container Apps, GitHub Actions workflows, service principals, Cloudflare DNS configuration, and SSL certificate provisioning via TXT validation.
