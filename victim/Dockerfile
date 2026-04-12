FROM httpd:2.4-alpine

# Include a custom config for demo tuning, logging and server-status.
COPY victim.conf /usr/local/apache2/conf/extra/victim.conf
RUN echo "Include conf/extra/victim.conf" >> /usr/local/apache2/conf/httpd.conf

# Demo website + lightweight health endpoint used by the page.
COPY www/ /usr/local/apache2/htdocs/