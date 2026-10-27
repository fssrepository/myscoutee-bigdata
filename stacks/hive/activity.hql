CREATE DATABASE IF NOT EXISTS myscoutee_lab;
USE myscoutee_lab;
CREATE TABLE IF NOT EXISTS activity_events (
  event_id STRING,
  occurred_at STRING,
  event_key STRING,
  actor_id STRING,
  city STRING,
  mode STRING
)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE;
LOAD DATA LOCAL INPATH '/opt/lab/activity.csv' OVERWRITE INTO TABLE activity_events;
SELECT event_key, COUNT(*) AS events FROM activity_events GROUP BY event_key ORDER BY event_key;
SELECT city, mode, COUNT(*) AS joins FROM activity_events
  WHERE event_key = 'event.member.joined'
  GROUP BY city, mode ORDER BY city, mode;
