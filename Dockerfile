FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/engineering
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY . .
ARG CBSETUP_EXTRAS="minimal"
ARG CBSETUP_INSTALL_MODE="static"
RUN case "$CBSETUP_EXTRAS" in minimal|cgc|sourcegraph|all) ;; *) exit 2 ;; esac; \
    case "$CBSETUP_INSTALL_MODE" in static|editable) ;; *) exit 2 ;; esac; \
    target="."; if [ "$CBSETUP_EXTRAS" != minimal ]; then target=".[$CBSETUP_EXTRAS]"; fi; \
    if [ "$CBSETUP_INSTALL_MODE" = editable ]; then \
      python -m pip install --no-cache-dir --editable "$target"; \
    else python -m pip install --no-cache-dir "$target"; fi
ARG SPEC_KIT_REF=""
RUN if [ -n "$SPEC_KIT_REF" ]; then \
      python setup_tooling.py --mode venv --speckit-ref "$SPEC_KIT_REF" --export-record /opt/engineering/toolchain.json --apply; \
    else \
      python -c "from codebase_agent_setup import toolchains; toolchains.write_record('toolchain.json', toolchains.resolve_selection())"; \
    fi
RUN chmod 644 /opt/engineering/toolchain.json
ENTRYPOINT ["python", "/opt/engineering/docker_install.py"]
CMD ["--help"]
