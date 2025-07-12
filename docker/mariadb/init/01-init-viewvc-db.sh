#!/bin/bash
# Database initialization script for ViewVC
# This script runs automatically when the MariaDB container starts for the first time

set -e

echo "Initializing ViewVC database..."

# Wait for MySQL to be ready
until mysql -h localhost -u root -p"$MYSQL_ROOT_PASSWORD" -e "SELECT 1" >/dev/null 2>&1; do
    echo "Waiting for MySQL to be ready..."
    sleep 2
done

echo "MySQL is ready. Setting up ViewVC database..."

# Create ViewVC database if it doesn't exist (should already be created by MYSQL_DATABASE env var)
mysql -h localhost -u root -p"$MYSQL_ROOT_PASSWORD" <<EOF
-- Ensure database exists with proper character set
CREATE DATABASE IF NOT EXISTS \`$MYSQL_DATABASE\` \
    CHARACTER SET utf8 \
    COLLATE utf8_unicode_ci;

-- Grant full privileges on database
CREATE USER IF NOT EXISTS '$VIEWVC_MYSQL_USER'@'%' IDENTIFIED BY '$VIEWVC_MYSQL_PASSWORD';
GRANT ALL PRIVILEGES ON \`$MYSQL_DATABASE\`.* TO '$VIEWVC_MYSQL_USER'@'%';

-- Create and grant read-only user privileges
CREATE USER IF NOT EXISTS '$VIEWVC_MYSQL_READONLY_USER'@'%' IDENTIFIED BY '$VIEWVC_MYSQL_READONLY_PASSWORD';
GRANT SELECT ON \`$MYSQL_DATABASE\`.* TO '$VIEWVC_MYSQL_READONLY_USER'@'%';

-- Apply privilege changes
FLUSH PRIVILEGES;

-- Show databases and users for verification
SHOW DATABASES;
SELECT User, Host FROM mysql.user WHERE User LIKE 'viewvc%';

EOF

echo "ViewVC database initialization completed successfully!"
