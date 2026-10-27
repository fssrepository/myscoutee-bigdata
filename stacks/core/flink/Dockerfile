FROM flink:2.2.1-scala_2.12
ADD --checksum=sha256:5605c691d11a501382c383fecba37a7a552467da5ab7ba904ef5d6f3d62c5616 https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-connector-kafka/5.0.0-2.2/flink-sql-connector-kafka-5.0.0-2.2.jar /opt/flink/lib/flink-sql-connector-kafka.jar
USER root
RUN chmod 644 /opt/flink/lib/flink-sql-connector-kafka.jar \
    && mkdir -p /opt/flink/checkpoints \
    && chown flink:flink /opt/flink/checkpoints
USER flink
