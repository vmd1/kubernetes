#!/bin/sh
# Keeps /lists in step with the blocklist controller. Runs next to dnsdist on every edge node.
#   <name>.txt  plain domains, one per line (what dnsdist loads)
#   <name>.sha  sha256 of that file; written last, so dnsdist only loads a list that downloaded completely
#   index       copy of the controller's index (name, sha256, entries); dnsdist re-reads it every minute
# A failed poll or download changes nothing: the lists already on disk keep being served.
set -u
URL="${CONTROLLER_URL:?CONTROLLER_URL is required}"
DIR="${LISTS_DIR:-/lists}"
INTERVAL="${INTERVAL:-60}"
TAB="$(printf '\t')"

sync_once() {
  wget -q -T 15 -O "$DIR/.index.new" "$URL/index.txt" || { echo "index fetch failed"; return 1; }

  # forget lists that were deleted from the cluster
  for f in "$DIR"/*.txt; do
    [ -e "$f" ] || continue
    n="$(basename "$f" .txt)"
    grep -q "^$n$TAB" "$DIR/.index.new" || { echo "removing $n"; rm -f "$DIR/$n.txt" "$DIR/$n.sha"; }
  done

  while IFS="$TAB" read -r name sha entries; do
    [ -n "$name" ] || continue
    [ "$(cat "$DIR/$name.sha" 2>/dev/null)" = "$sha" ] && [ -e "$DIR/$name.txt" ] && continue
    echo "fetching $name ($entries entries)"
    if wget -q -T 120 -O "$DIR/.$name.gz" "$URL/lists/$name.txt.gz" \
       && gunzip -c "$DIR/.$name.gz" > "$DIR/.$name.txt" \
       && [ "$(sha256sum "$DIR/.$name.txt" | cut -d' ' -f1)" = "$sha" ]; then
      mv "$DIR/.$name.txt" "$DIR/$name.txt"
      echo "$sha" > "$DIR/$name.sha"
    else
      echo "download of $name failed or did not match its checksum; keeping the old list"
    fi
    rm -f "$DIR/.$name.gz" "$DIR/.$name.txt"
  done < "$DIR/.index.new"

  mv "$DIR/.index.new" "$DIR/index"
}

trap 'exit 0' TERM INT
while true; do
  sync_once
  sleep "$INTERVAL" &
  wait $!
done
