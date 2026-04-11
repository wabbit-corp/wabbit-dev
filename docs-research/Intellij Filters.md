```python
# src[one.wabbit.cc4*]:*..*||test[one.wabbit.cc4*]:*..*||src[one.wabbit.cc-plugin-main*]:*..*||test[one.wabbit.cc-plugin-main*]:*..*||src[one.wabbit.cc-lib-math*]:*..*||test[one.wabbit.cc-lib-math*]:*..*||src[one.wabbit.kotlin-lang-mu*]:*..*||test[one.wabbit.kotlin-lang-mu*]:*..*
# file[one.wabbit.kotlin-clipboard]:src/
import re
projects = ["app-wdev", "kotlin-clipboard", "kotlin-fnmatch", "kotlin-web-jitpack", "kotlin-filetypes"]

result = '||'.join([f'file[one.wabbit.{p}.main]:kotlin//*||file[one.wabbit.{p}.test]:kotlin//*||src[one.wabbit.{p}]:*||test[one.wabbit.{p}]:*..*' for p in projects])
print(result)
```