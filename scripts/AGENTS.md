Start and stop the local Docker app.

- Mac: start-mac.sh, stop-mac.sh
- Linux: start-linux.sh, stop-linux.sh
- Windows: start-windows.ps1, stop-windows.ps1

Each start script builds the image, replaces the `pm-app` container, and publishes port 8000. Stop scripts remove that container.
