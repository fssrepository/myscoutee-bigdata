# Big Data Lab Guide

`MyScoutee_Big_Data_Lab_Guide_EN.pdf` is the branded, versioned guide for this
repository. It describes the runnable sandbox, reviews the original 12
technologies with MyScoutee-specific exercises and proposed optional stations,
adds an optional Avro and Schema Registry exercise with a worked event schema,
and covers integration contracts and replacement decision gates. The source is
`build-guide.py`; the logo asset is in `assets/heart.png`.

Regenerate after editing the guide source:

```sh
python3 guides/publication/manuals/build-guide.py
```

The generator needs ReportLab and the DejaVu Sans fonts. Review the rendered
PDF pages after changing content or layout. The document describes lab
behavior, not a production integration with the MyScoutee backend.
