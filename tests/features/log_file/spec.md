# log_file — test contract (FIBR-0410)

design.md § Observability promises a local rotating log file in the user data
directory, its path shown in Settings. Locked here:

- **INV-1:** `install_log_file(directory)` writes the `finbreak` logger's
  records to `directory/finbreak.log`, owner-only (0600), rotating.
- **INV-2:** installing twice adds one handler, not two.
- **INV-3:** a directory that cannot hold the file does not stop the app;
  the call returns `None`.
- **INV-4:** `app.run()` installs it, and Settings shows the path.
