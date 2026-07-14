# Package Example Data

`NutritionEx.pdf` is the canonical package copy of the Creative Commons paper
used for parser corpus checks and the planned R-package vignette. Do not keep a
second copy under the external `testpapers` directory.

From an installed R package, locate it with:

```r
system.file("extdata", "NutritionEx.pdf", package = "parseTable1")
```

The PDF remains the raw source artifact. Parser JSON outputs generated from it
belong under the ignored `outputs/` directory and are not package data.
