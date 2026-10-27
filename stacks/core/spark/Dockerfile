FROM apache/spark:4.0.4-scala2.13-java17-python3-ubuntu
ARG LAB_UID=1000
ARG LAB_GID=1000
USER root
RUN groupadd --gid "$LAB_GID" lab && useradd --uid "$LAB_UID" --gid "$LAB_GID" --create-home lab
USER lab
