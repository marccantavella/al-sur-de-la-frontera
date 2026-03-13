---
title: "How I built this blog: Docker, Azure, GitHub Actions and Cloudflare from scratch"
date: 2026-03-13
excerpt: "A complete technical walkthrough of every step I followed to build a static blog with automated deployment. No shortcuts, errors included."
---

This post documents, step by step, how I built the infrastructure behind this blog. This is not a simplified tutorial: it includes every command I ran, every error I hit, and how I fixed it. I'm writing this for my future self and for anyone who wants to learn by doing.

The goal was simple: a static blog where publishing is as easy as writing a markdown file and running git push. The interesting part is everything that happens behind the scenes to make that work.

## The idea

I wanted to train myself as a Cloud/DevOps Engineer by building something real. The plan: a personal blog deployed with production-grade technologies. No WordPress, no Netlify. The full stack, by hand.

**Stack chosen:**
- Python for a build script that converts markdown to HTML
- Docker to package the site in a container with Nginx
- Azure Container Registry to store Docker images
- Azure Container Apps to serve the site
- GitHub Actions to automate the build and deployment
- Cloudflare for DNS and SSL certificate
- A custom domain: alsurdelafrontera.org

## Project structure

Before writing any code, I defined the file structure:

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

The key insight about this architecture is the separation between **build time** and **serve time**. The Python script, the markdown files, and the template only exist during the build. The final Docker container only contains Nginx, the generated `index.html`, and the CSS file. Visitors never see the build tools.

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

**The HTML template** (`templates/base.html`) is the blog's design with a placeholder `__POSTS_DATA__` where the build script injects the post data as a JavaScript JSON array. The CSS is extracted into a separate file (`static/style.css`) so the browser can cache it independently.

**The build script** (`build.py`) does the following:
1. Scans the `posts/` folder for `.md` files
2. For each file, separates the frontmatter (YAML) from the body (markdown)
3. Converts the markdown body to HTML using the `markdown` library
4. Formats dates in Spanish (e.g., "12 mar 2026")
5. Sorts posts by date, newest first
6. Serializes everything as JSON and injects it into the template
7. Outputs the final `output/index.html`

The only dependencies are `markdown` and `pyyaml`, listed in `requirements.txt`.

I tested the script locally with `python build.py` and it generated the `index.html` correctly with all three posts.

## Step 2: Docker and Nginx

The goal here was to package the site into a container that could run on any server.

**`nginx.conf`** configures Nginx to serve static files on port 80, with a 7-day cache for CSS files. It's a minimal configuration — just enough to serve a blog.

**The Dockerfile** uses two stages (multi-stage build):
- **Stage 1 (builder):** Uses a Python 3.12 slim image, installs the dependencies, copies the source files, and runs `build.py`. This generates the `index.html`.
- **Stage 2 (server):** Uses an Nginx Alpine image (~7MB), copies ONLY the generated HTML and CSS from stage 1. Python, the build script, and the markdown files never make it to the final container.

The result: a ~40MB image containing only Nginx and static files.

**`.dockerignore`** excludes unnecessary files from the build context: `.git`, `README.md`, the `output/` folder, editor files, etc.

**Local test on Windows:**

```
docker build -t alsurdelafrontera:test .
docker run -p 8080:80 alsurdelafrontera:test
```

I opened `http://localhost:8080` and the blog worked perfectly. The build took 7.7 seconds and completed all 22 steps.

## Step 3: Azure — creating the infrastructure

### Installing Azure CLI

```
winget install -e --id Microsoft.AzureCLI
```

After installing, I closed and reopened the terminal so it would recognize the `az` command.

### Logging into Azure

The first attempt with `az login` failed with a Windows Account Manager (WAM) error:

```
Unexpected exception while waiting for accounts control to finish:
'A specified logon session does not exist. It may already have been terminated.'
```

Running `az logout` followed by `az login` again produced the same error. The fix was to bypass the WAM broker entirely using the device code flow:

```
az login --use-device-code
```

This displays a code and a URL. I opened the URL in my browser, entered the code, and authenticated successfully. The terminal showed my subscription: "Azure subscription 1" in the "Spain Central" region.

### Creating the Resource Group

A Resource Group is a logical container in Azure that groups related resources together. Everything we create goes inside it.

```
az group create --name rg-alsurdelafrontera --location spaincentral
```

### Creating the Container Registry

```
az acr create --name alsurdelafrontera --resource-group rg-alsurdelafrontera --sku Basic --admin-enabled true
```

**This failed** with a `MissingSubscriptionRegistration` error: the subscription wasn't registered to use the `Microsoft.ContainerRegistry` namespace. This is normal for new Azure subscriptions — resource providers need to be registered before you can use them.

I fixed it by registering the necessary providers:

```
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
```

I waited for the status to change to "Registered" by checking:

```
az provider show --namespace Microsoft.ContainerRegistry --query "registrationState"
```

Then I re-ran the registry creation command and it succeeded.

**What each parameter does:**
- `--name alsurdelafrontera` — name of the registry, which becomes the URL `alsurdelafrontera.azurecr.io`
- `--sku Basic` — cheapest tier (~5-7€/month), includes 10GB of storage
- `--admin-enabled true` — enables simple username/password authentication for Docker

### Pushing the Docker image to Azure

First, I logged Docker into the registry:

```
az acr login --name alsurdelafrontera
```

Then tagged and pushed the local image:

```
docker tag alsurdelafrontera:test alsurdelafrontera.azurecr.io/blog:v1
docker push alsurdelafrontera.azurecr.io/blog:v1
```

### Deploying to Container Apps

```
az containerapp up --name blog-alsurdelafrontera --resource-group rg-alsurdelafrontera --location spaincentral --image alsurdelafrontera.azurecr.io/blog:v1 --target-port 80 --ingress external
```

This single command created three resources automatically:
- A Container Apps environment (`blog-alsurdelafrontera-env`) — the infrastructure layer
- A Log Analytics workspace — for collecting container logs
- The container app itself (`blog-alsurdelafrontera`) — running my Nginx image

When it finished, Azure gave me a public URL:
`https://blog-alsurdelafrontera.salmonsky-5b6d2ef3.spaincentral.azurecontainerapps.io`

The blog was on the internet.

### Resources created and cost breakdown

Running `az resource list --resource-group rg-alsurdelafrontera --output table` showed four resources:

| Resource | Type | Monthly cost |
|----------|------|-------------|
| alsurdelafrontera | Container Registry (Basic) | ~€5-7 |
| workspace-rgalsurdelafronteraKImU | Log Analytics workspace | €0 (free tier, 5GB/month) |
| blog-alsurdelafrontera-env | Container Apps environment | €0 (Consumption plan) |
| blog-alsurdelafrontera | Container App | ~€0-1 (free tier covers it) |

**Total estimated cost: ~€5-8/month**, almost entirely from the Container Registry. The Container App itself has generous free grants: 180,000 vCPU-seconds, 360,000 GiB-seconds, and 2 million requests per month. A personal blog will never come close to those limits.

## Step 4: GitHub Actions — automating the deployment

### Installing Git and creating the repository

I already had Git Bash installed (which includes Git), so I verified with `git --version` and configured my identity:

```
git config --global user.name "My Name"
git config --global user.email "marccantavella@users.noreply.github.com"
```

I created a public repository on GitHub called `al-sur-de-la-frontera` with no README or .gitignore, then initialized the local repository:

```
git init
git add .
git commit -m "Initial commit: blog with build script and Dockerfile"
git branch -M main
git remote add origin https://github.com/marccantavella/al-sur-de-la-frontera.git
git push -u origin main
```

**The push failed** with error `GH007: Your push would publish a private email address.` GitHub's email privacy protection was blocking it because my git config used my real email. I fixed it by using GitHub's no-reply address:

```
git config --global user.email "marccantavella@users.noreply.github.com"
git commit --amend --reset-author --no-edit
git push -u origin main
```

### Setting up GitHub Secrets

GitHub Actions needs credentials to interact with Azure. First, I got the Container Registry credentials:

```
az acr credential show --name alsurdelafrontera --output table
```

This outputs a username and two passwords (Azure generates two so you can rotate one without downtime). I used the first password.

Then I created a service principal — essentially a robot account for GitHub Actions to authenticate with Azure:

```
az ad sp create-for-rbac --name "github-deploy-blog" --role contributor --scopes /subscriptions/MY-SUBSCRIPTION-ID/resourceGroups/rg-alsurdelafrontera --sdk-auth
```

This outputs a JSON blob with the credentials.

I added 4 secrets in GitHub (repository Settings → Secrets and variables → Actions → New repository secret):
- `ACR_USERNAME` — the Container Registry username
- `ACR_PASSWORD` — the first Container Registry password
- `ACR_LOGIN_SERVER` — `alsurdelafrontera.azurecr.io`
- `AZURE_CREDENTIALS` — the complete JSON blob from the service principal

### The workflow file (deploy.yml)

I created `.github/workflows/deploy.yml` with these steps:
1. **Checkout code** — pulls the latest code from the repository
2. **Log in to ACR** — authenticates Docker with the Container Registry
3. **Build Docker image** — runs `docker build`, tags with both `latest` and the commit SHA for traceability
4. **Push to ACR** — uploads the image to the registry
5. **Azure Login** — authenticates with Azure using the service principal
6. **Deploy to Container Apps** — runs `az containerapp update` to pull the new image

### First run: failure and fix

**The first pipeline run failed.** Steps 1-4 (checkout, ACR login, build, push) all succeeded. But step 5 ("Deploy to Container Apps") failed with:

```
ERROR: Please run 'az login' to setup account.
```

The problem: the original workflow was missing an explicit Azure login step. The `azure/cli@v2` action doesn't automatically authenticate — you need to call `azure/login@v2` first with the `AZURE_CREDENTIALS` secret.

I added the missing Azure Login step between "Push to ACR" and "Deploy to Container Apps", committed the fix, and pushed:

```
git add .
git commit -m "Fix: add Azure login step to workflow"
git push
```

The second run was all green. The pipeline completed in 1 minute and 11 seconds.

### Testing the full loop

To prove the entire pipeline worked end-to-end, I created a new post: `posts/2026-03-13-mi-primer-deploy.md`. I committed and pushed.

**It didn't work.** The pipeline ran successfully (green check), but the new post didn't appear on the blog. After investigating, I found the problem: Windows had saved the file as `2026-03-13-mi-primer-deploy.md.txt` (double extension). The build script only reads files ending in `.md`, so it was being ignored.

The fix:

```
Rename-Item "2026-03-13-mi-primer-deploy.md.txt" "2026-03-13-mi-primer-deploy.md"
git add .
git commit -m "Fix: rename post file from .md.txt to .md"
git push
```

After the pipeline ran, the new post appeared on the blog. The full loop was working.

**Lesson learned:** When saving files in Windows text editors, always change "Save as type" to "All Files (*.*)" to prevent Windows from silently adding `.txt`.

## Step 5: Custom domain with Cloudflare

The final step was pointing my domain `alsurdelafrontera.org` to the Azure container.

### DNS records in Cloudflare

I added two records in Cloudflare's DNS dashboard:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| TXT | asuid | (Azure's domain verification ID) | DNS only |
| CNAME | @ | blog-alsurdelafrontera.salmonsky-5b6d2ef3.spaincentral.azurecontainerapps.io | DNS only |

The verification ID came from:

```
az containerapp show --name blog-alsurdelafrontera --resource-group rg-alsurdelafrontera --query "properties.customDomainVerificationId" --output tsv
```

Both records were set to **DNS only** (gray cloud, not orange) for the initial setup.

### Adding the hostname to Azure

```
az containerapp hostname add --name blog-alsurdelafrontera --resource-group rg-alsurdelafrontera --hostname alsurdelafrontera.org
```

### Binding the SSL certificate

The first attempt with CNAME validation failed because root domains don't support it:

```
az containerapp hostname bind ... --validation-method CNAME
(InvalidValidationMethod) Invalid validation method for domain 'alsurdelafrontera.org'.
Supported validation method(s) for the domain are: HTTP, TXT.
```

I switched to TXT validation:

```
az containerapp hostname bind --name blog-alsurdelafrontera --resource-group rg-alsurdelafrontera --hostname alsurdelafrontera.org --environment blog-alsurdelafrontera-env --validation-method TXT
```

Azure provided a TXT token to add to Cloudflare:

| Type | Name | Content |
|------|------|---------|
| TXT | _dnsauth | (token provided by Azure) |

The certificate provisioning can take up to 20 minutes. Once complete, the site was available at `https://alsurdelafrontera.org`.

## The result

From any computer with Git installed, my workflow is now:

1. Create a new `.md` file in `posts/`
2. `git add . → git commit → git push`
3. Wait ~2 minutes
4. Post is live at alsurdelafrontera.org

Everything between "push" and "live" is automatic: GitHub Actions detects the push, builds the Docker image (which runs the Python script inside), pushes it to Azure Container Registry, and updates the Container App. No manual intervention, no servers to manage, no FTP, no SSH.

The total monthly cost is ~€5-8, almost entirely from the Container Registry. And I learned Docker, multi-stage builds, Nginx configuration, Azure CLI, resource providers, Container Apps, GitHub Actions workflows, service principals, DNS configuration, and SSL certificate provisioning — all from building one blog.

That's the point. The blog is simple. The infrastructure is the education.
