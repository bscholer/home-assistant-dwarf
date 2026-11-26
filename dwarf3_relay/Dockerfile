# The relay image is published from bscholer/dwarf-relay on a v* tag. Versions before 0.6.0
# were published as ghcr.io/bscholer/dwarf3-control, the repository's old name.
FROM ghcr.io/bscholer/dwarf-relay:0.6.2
COPY run.py /run.py
ENTRYPOINT ["python", "/run.py"]
