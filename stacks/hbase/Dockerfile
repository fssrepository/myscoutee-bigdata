FROM eclipse-temurin:17-jre-jammy

ARG HBASE_VERSION=3.0.0
ARG HBASE_SHA512=8290BC3CECE084D36F7F47AAE726268C7332E4828C6E8599DF1343B03348E93F91165FAD03AC6107BFBF0D8535E72024FA5D19217890D2848D013D8418A584ED

RUN apt-get update && apt-get install -y --no-install-recommends curl procps \
    && curl --retry 3 -fsSL "https://archive.apache.org/dist/hbase/${HBASE_VERSION}/hbase-${HBASE_VERSION}-bin.tar.gz" -o /tmp/hbase.tar.gz \
    && echo "${HBASE_SHA512}  /tmp/hbase.tar.gz" | sha512sum -c - \
    && mkdir -p /opt/hbase \
    && tar -xzf /tmp/hbase.tar.gz -C /opt/hbase --strip-components=1 \
    && rm /tmp/hbase.tar.gz \
    && apt-get clean \
    && rm -r /var/lib/apt/lists/*

ENV HBASE_HOME=/opt/hbase
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH=/opt/hbase/bin:$PATH

COPY hbase-site.xml /opt/hbase/conf/hbase-site.xml

EXPOSE 16010
CMD ["/bin/bash", "-lc", "start-hbase.sh && tail -F /opt/hbase/logs/*"]
