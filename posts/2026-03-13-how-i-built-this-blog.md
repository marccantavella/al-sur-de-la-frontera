\---

title: "How I built this blog: Docker, Azure, GitHub Actions and Cloudflare from scratch"
date: 2026-03-13
excerpt: "A complete technical walkthrough of every step required to build a static blog with automated deployment. No shortcuts, errors included."
---

This post documents, step by step, how the infrastructure behind this blog was built. This is not a simplified tutorial: it includes every command executed, every error encountered, and how each was resolved.

The goal: a static blog where publishing is as easy as writing a markdown file and running `git push`. Everything between "push" and "live" is automated.

## Stack overview

* Python for a build script that converts markdown to HTML
* Docker to package the site in a container with Nginx
* Azure Container Registry to store Docker images
* Azure Container Apps to serve the site
* GitHub Actions to automate the build and deployment
* Cloudflare for DNS and SSL certificate
* Custom domain: alsurdelafrontera.org

