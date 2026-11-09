# Obsidian Sync Server (removed)

The CouchDB server (obsidian-sync) was removed on 2026-11-09 to free memory on hades-01. Only the 10 Gi `obsidian-pvc` is kept (`pvc.yaml`), so the data survives. Delete `pvc.yaml` when the notes are confirmed safe on the clients; Flux then prunes the volume. Restore the server from git history (`git log -- resources/personal/obsidian`).
