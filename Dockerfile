# ===========================================================================
# Dockerfile — Two-stage build for the blog
#
# Stage 1 ("builder"): Uses Python to run build.py and generate index.html
# Stage 2 ("server"):  Uses Nginx to serve the generated static files
#
# Why two stages? The final image only contains Nginx + your HTML/CSS.
# Python, build.py, the markdown files — none of that ships to production.
# This keeps the image tiny (~40MB) and fast to deploy.
# ===========================================================================


# ---------------------------------------------------------------------------
# STAGE 1: Build the site
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Set the working directory inside the container
WORKDIR /app

# Copy and install Python dependencies first.
# Docker caches each step. By copying requirements.txt before the rest
# of the code, Docker only re-installs packages when requirements change —
# not every time you edit a blog post.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the source files needed for the build
COPY build.py .
COPY posts/ posts/
COPY templates/ templates/
COPY static/ static/

# Run the build script — this generates output/index.html
RUN python build.py


# ---------------------------------------------------------------------------
# STAGE 2: Serve with Nginx
# ---------------------------------------------------------------------------
FROM nginx:alpine

# Remove the default Nginx welcome page
RUN rm -rf /usr/share/nginx/html/*

# Copy our custom Nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Copy the build output (index.html) from stage 1
COPY --from=builder /app/output/index.html /usr/share/nginx/html/

# Copy static assets (CSS)
COPY --from=builder /app/static/ /usr/share/nginx/html/static/

# Nginx listens on port 80
EXPOSE 80

# Start Nginx in the foreground (required for Docker — if Nginx
# runs as a background daemon, the container exits immediately)
CMD ["nginx", "-g", "daemon off;"]
