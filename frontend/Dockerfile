FROM nginx:1.25-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf

# One COPY per source: with multiple sources in a single COPY, Docker
# copies only the *contents* of each directory flat into the destination,
# discarding the css/js/pages folder names themselves. That
# broke every /js/*.js and /css/*.css request in production (404 -> SPA
# fallback served index.html -> browser rejected the wrong MIME type).
COPY index.html /usr/share/nginx/html/
COPY css/*.css /usr/share/nginx/html/css/
COPY js/*.js /usr/share/nginx/html/js/
COPY pages/*.html /usr/share/nginx/html/pages/

EXPOSE 80
