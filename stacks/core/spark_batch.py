"""Read Kafka history and write deduplicated daily aggregates as Parquet."""

import os

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T


def main():
    spark = (SparkSession.builder.appName("MyScoutee activity history")
             .config("spark.sql.session.timeZone", "UTC")
             .config("spark.hadoop.fs.s3a.endpoint", "http://lake:8333")
             .config("spark.hadoop.fs.s3a.endpoint.region", "us-east-1")
             .config("spark.hadoop.fs.s3a.path.style.access", "true")
             .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
             .config("spark.hadoop.fs.s3a.aws.credentials.provider", "software.amazon.awssdk.auth.credentials.EnvironmentVariableCredentialsProvider")
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    schema = T.StructType([
        T.StructField("event_id", T.StringType()),
        T.StructField("occurred_at", T.StringType()),
        T.StructField("event_key", T.StringType()),
        T.StructField("actor_id", T.StringType()),
        T.StructField("activity_id", T.StringType()),
        T.StructField("city", T.StringType()),
        T.StructField("mode", T.StringType()),
        T.StructField("group_id", T.StringType()),
        T.StructField("amount", T.IntegerType()),
    ])
    rows = (spark.read.format("kafka")
            .option("kafka.bootstrap.servers", os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092"))
            .option("subscribe", os.environ.get("KAFKA_TOPIC", "myscoutee.activity.v1"))
            .option("startingOffsets", "earliest")
            .option("endingOffsets", "latest")
            .load())
    events = (rows.select(F.from_json(F.col("value").cast("string"), schema).alias("e"))
              .select("e.*")
              .filter(F.col("event_id").isNotNull() & F.col("event_key").isNotNull())
              .dropDuplicates(["event_id"])
              .withColumn("day", F.to_date("occurred_at")))
    daily = (events.groupBy("day", "city", "mode", "event_key")
             .agg(F.count("*").alias("events"), F.countDistinct("actor_id").alias("actors")))
    target = "s3a://myscoutee-lake/daily_activity"
    daily.write.mode("overwrite").partitionBy("day").parquet(target)
    written = spark.read.parquet(target)
    print(f"Wrote {written.count()} daily aggregate rows to {target}")
    spark.stop()


if __name__ == "__main__":
    main()
