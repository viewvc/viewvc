FROM mariadb:10.11

# Copy ViewVC-optimized MariaDB configuration and set permissions
COPY docker/mariadb/my.cnf /etc/mysql/conf.d/viewvc.cnf
RUN chmod 644 /etc/mysql/conf.d/viewvc.cnf

# Copy database initialization scripts
COPY docker/mariadb/init/ /docker-entrypoint-initdb.d/

# Create log directory with proper permissions
RUN mkdir -p /var/log/mysql && chown mysql:mysql /var/log/mysql

# Expose MySQL port
EXPOSE 3306

# Use the default MariaDB entrypoint
# The configuration and init scripts will be automatically loaded
