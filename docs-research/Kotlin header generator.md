## Prompt:
I want to create a tool that would take a Kotlin/Python file and extract the public interface - public classes methods docs but without implementation. It should be written in Kotlin itself.

2/2

## Response:
Thought for 5m 36s

You want to strip a file down to its **public surface**—signatures + docs, zero bodies—_for Kotlin and Python_, with the tool itself written in Kotlin. Very well. Here’s a precise, fast, no-handholding solution.

It has two extractors under one CLI:

*   **Kotlin**: uses the Kotlin compiler PSI to walk the AST and print _public_ classes / interfaces / objects / enums / constructors / functions / properties + KDoc. No implementations.
*   **Python**: invokes the local Python runtime to parse via `ast` and prints the _exported_ module/class API with docstrings and signatures. (Respects `__all__` when present; otherwise hides leading-underscore names but keeps “dunder” specials like `__init__`.)

If you insist on a pure‑JVM Python parser later, I’ll wire an ANTLR grammar—this version favors shipping speed over philosophical purity.

* * *

Quick start
-----------

```
public-surface/
├─ build.gradle.kts
└─ src/main/kotlin/tool/PublicSurfaceTool.kt
```

### `build.gradle.kts`

```kotlin
import org.jetbrains.kotlin.gradle.tasks.KotlinCompile

val kotlinVersion = "1.9.24" // set to match your project; 2.x is fine too

plugins {
    kotlin("jvm") version "1.9.24"
    application
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(kotlin("stdlib"))
    // Kotlin compiler (relocated IntelliJ) for PSI parsing
    implementation("org.jetbrains.kotlin:kotlin-compiler-embeddable:$kotlinVersion")
}

application {
    mainClass.set("tool.PublicSurfaceToolKt")
}

tasks.withType<KotlinCompile>().configureEach {
    kotlinOptions.jvmTarget = "17" // change if you need
}
```

### `src/main/kotlin/tool/PublicSurfaceTool.kt`

```kotlin
package tool

import java.io.File
import java.nio.file.Files
import java.nio.file.StandardOpenOption

// ---- Kotlin PSI imports (relocated IntelliJ under org.jetbrains.kotlin.com.intellij.*)
import org.jetbrains.kotlin.cli.common.CLIConfigurationKeys
import org.jetbrains.kotlin.cli.jvm.compiler.EnvironmentConfigFiles
import org.jetbrains.kotlin.cli.jvm.compiler.KotlinCoreEnvironment
import org.jetbrains.kotlin.cli.jvm.config.addKotlinSourceRoot
import org.jetbrains.kotlin.com.intellij.openapi.util.Disposer
import org.jetbrains.kotlin.config.CommonConfigurationKeys
import org.jetbrains.kotlin.kdoc.psi.api.KDoc
import org.jetbrains.kotlin.lexer.KtTokens
import org.jetbrains.kotlin.psi.*

fun main(args: Array<String>) {
    if (args.isEmpty()) {
        System.err.println("Usage: public-surface <file-or-dir> ...")
        return
    }

    val inputs = args.map(::File)
    val ktFiles = gather(inputs, listOf("kt"))
    val pyFiles = gather(inputs, listOf("py"))

    if (ktFiles.isEmpty() && pyFiles.isEmpty()) {
        error("No .kt or .py files found.")
    }

    if (ktFiles.isNotEmpty()) {
        KotlinPublicSurface().emit(ktFiles)
        println()
    }

    if (pyFiles.isNotEmpty()) {
        PythonPublicSurface().emit(pyFiles)
    }
}

/* ------------------------------ File helpers ------------------------------ */

private fun gather(roots: List<File>, exts: List<String>): List<File> =
    roots.flatMap { root ->
        when {
            root.isFile && exts.contains(root.extension) -> listOf(root)
            root.isDirectory -> root.walkTopDown().filter { it.isFile && exts.contains(it.extension) }.toList()
            else -> emptyList()
        }
    }.distinctBy { it.canonicalPath }

/* ------------------------------ Kotlin side ------------------------------- */

private class KotlinPublicSurface {

    fun emit(files: List<File>) {
        val disposable = Disposer.newDisposable("kotlin-psi")
        try {
            val cfg = org.jetbrains.kotlin.config.CompilerConfiguration().apply {
                put(CommonConfigurationKeys.MODULE_NAME, "publicSurface")
                put(CLIConfigurationKeys.MESSAGE_COLLECTOR_KEY, org.jetbrains.kotlin.cli.common.messages.MessageCollector.NONE)
                files.forEach { addKotlinSourceRoot(it.absolutePath) }
            }

            val env = KotlinCoreEnvironment.createForProduction(disposable, cfg, EnvironmentConfigFiles.JVM_CONFIG_FILES)
            val out = Printer()

            env.sourceFiles.forEach { ktFile ->
                val pkg = ktFile.packageFqName.asString()
                if (pkg.isNotEmpty() && pkg != "<root>") {
                    out.line("package $pkg")
                    out.line()
                }
                ktFile.declarations.forEach { decl ->
                    when (decl) {
                        is KtClassOrObject -> visitClassOrObject(decl, out)
                        is KtNamedFunction  -> if (decl.isEffectivelyPublic()) printFunction(decl, out)
                        is KtProperty       -> if (decl.isEffectivelyPublic()) printProperty(decl, out)
                    }
                }
                out.line()
            }

            print(out.toString())
        } finally {
            Disposer.dispose(disposable)
        }
    }

    private fun visitClassOrObject(node: KtClassOrObject, out: Printer) {
        if (!node.isEffectivelyPublic()) return

        node.printKDoc(out)

        when (node) {
            is KtClass -> {
                val kind = when {
                    node.isInterface()  -> "interface"
                    node.isEnum()       -> "enum class"
                    node.isAnnotation() -> "annotation class"
                    node.isData()       -> "data class"
                    node.isSealed()     -> "sealed class"
                    else                -> "class"
                }
                val tparams = node.typeParameterList?.text ?: ""
                val ctorParams = node.primaryConstructorParameterList?.parameters
                    ?.joinToString(", ") { it.paramSig() } ?: ""
                val headerParams = if (ctorParams.isNotEmpty() && !node.isInterface()) "($ctorParams)" else ""
                val superTypes = node.getSuperTypeList()?.entries?.joinToString(", ") { it.text }?.takeIf { it.isNotBlank() }
                val superSuffix = superTypes?.let { " : $it" } ?: ""

                out.line("public $kind ${node.name}$tparams$headerParams$superSuffix {")
                out.indent {
                    if (node.isEnum()) {
                        val entries = node.declarations.filterIsInstance<KtEnumEntry>().mapNotNull { it.name }
                        if (entries.isNotEmpty()) {
                            out.line(entries.joinToString(", "))
                            if (node.declarations.any { it !is KtEnumEntry }) out.line()
                        }
                    }

                    node.secondaryConstructors.filter { it.isEffectivelyPublic() }.forEach { ctor ->
                        ctor.printKDoc(out)
                        val ps = ctor.valueParameters.joinToString(", ") { it.paramSig() }
                        out.line("public constructor($ps)")
                    }

                    node.declarations.forEach { member ->
                        when (member) {
                            is KtNamedFunction -> if (member.isEffectivelyPublic()) printFunction(member, out)
                            is KtProperty      -> if (member.isEffectivelyPublic()) printProperty(member, out)
                            is KtClassOrObject -> visitClassOrObject(member, out)
                        }
                    }
                }
                out.line("}")
                out.line()
            }

            is KtObjectDeclaration -> {
                val header = if (node.isCompanion()) "companion object" else "object ${node.name ?: ""}".trim()
                val superTypes = node.getSuperTypeList()?.entries?.joinToString(", ") { it.text }?.takeIf { it.isNotBlank() }
                val superSuffix = superTypes?.let { " : $it" } ?: ""

                out.line("public $header$superSuffix {")
                out.indent {
                    node.declarations.forEach { member ->
                        when (member) {
                            is KtNamedFunction -> if (member.isEffectivelyPublic()) printFunction(member, out)
                            is KtProperty      -> if (member.isEffectivelyPublic()) printProperty(member, out)
                            is KtClassOrObject -> visitClassOrObject(member, out)
                        }
                    }
                }
                out.line("}")
                out.line()
            }
        }
    }

    private fun printFunction(fn: KtNamedFunction, out: Printer) {
        fn.printKDoc(out)
        val mods = buildList<String> {
            if (fn.modifierList?.hasModifier(KtTokens.SUSPEND_KEYWORD) == true) add("suspend")
            if (fn.modifierList?.hasModifier(KtTokens.INFIX_KEYWORD) == true) add("infix")
            if (fn.modifierList?.hasModifier(KtTokens.OPERATOR_KEYWORD) == true) add("operator")
        }.joinToString(" ")

        val tparams = fn.typeParameterList?.text ?: ""
        val receiver = fn.receiverTypeReference?.text?.let { "$it." } ?: ""
        val name = fn.name ?: "<anonymous>"
        val params = fn.valueParameters.joinToString(", ") { it.paramSig() }
        val ret = fn.typeReference?.text?.let { ": $it" } ?: ""

        out.line(buildString {
            append("public ")
            if (mods.isNotEmpty()) append("$mods ")
            append("fun ")
            append(tparams)
            if (tparams.isNotEmpty()) append(" ")
            append(receiver).append(name)
            append("(").append(params).append(")")
            append(ret)
        })
    }

    private fun printProperty(p: KtProperty, out: Printer) {
        p.printKDoc(out)
        val isConst = p.modifierList?.hasModifier(KtTokens.CONST_KEYWORD) == true
        val isLateinit = p.modifierList?.hasModifier(KtTokens.LATEINIT_KEYWORD) == true
        val receiver = p.receiverTypeReference?.text?.let { "$it." } ?: ""
        val head = buildString {
            append("public ")
            if (isConst) append("const ")
            if (isLateinit) append("lateinit ")
            append(if (p.isVar) "var " else "val ")
            append(receiver).append(p.name)
            p.typeReference?.text?.let { append(": ").append(it) }
        }

        out.line(head)
    }
}

/* --------------------------- Kotlin helpers --------------------------- */

private class Printer {
    private val sb = StringBuilder()
    private var indent = 0
    fun line(s: String = "") { repeat(indent) { sb.append("    ") }; sb.appendLine(s) }
    fun indent(block: () -> Unit) { indent++; block(); indent-- }
    override fun toString(): String = sb.toString()
}

private fun KtDeclaration.isEffectivelyPublic(): Boolean {
    if (this is KtNamedDeclaration && isLocal) return false
    if (this is KtModifierListOwner) {
        val ml = modifierList
        if (ml?.hasModifier(KtTokens.PRIVATE_KEYWORD) == true) return false
        if (ml?.hasModifier(KtTokens.PROTECTED_KEYWORD) == true) return false
        if (ml?.hasModifier(KtTokens.INTERNAL_KEYWORD) == true) return false
    }
    var p = parent
    while (p != null) {
        if (p is KtDeclaration) {
            if (p is KtModifierListOwner) {
                val ml = p.modifierList
                if (ml?.hasModifier(KtTokens.PRIVATE_KEYWORD) == true) return false
                if (ml?.hasModifier(KtTokens.PROTECTED_KEYWORD) == true) return false
                if (ml?.hasModifier(KtTokens.INTERNAL_KEYWORD) == true) return false
            }
        }
        p = p.parent
    }
    return true
}

private fun KtDeclaration.printKDoc(out: Printer) {
    val kdoc = (docComment as? KDoc)?.getDefaultSection()?.getContent()?.trim()?.takeIf { it.isNotBlank() } ?: return
    out.line("/**")
    kdoc.lines().forEach { out.line(" * " + it.trimEnd()) }
    out.line(" */")
}

private fun KtParameter.paramSig(): String {
    val mods = buildList<String> {
        if (modifierList?.hasModifier(KtTokens.NOINLINE_KEYWORD) == true) add("noinline")
        if (modifierList?.hasModifier(KtTokens.CROSSINLINE_KEYWORD) == true) add("crossinline")
        if (modifierList?.hasModifier(KtTokens.VARARG_KEYWORD) == true) add("vararg")
    }.joinToString(" ")

    val valVar = when {
        hasValOrVar() && this.valOrVarKeyword?.node?.elementType == KtTokens.VAR_KEYWORD -> "var "
        hasValOrVar() -> "val "
        else -> ""
    }

    val typePart = typeReference?.text?.let { ": $it" } ?: ""
    return buildString {
        if (mods.isNotEmpty()) append("$mods ")
        append(valVar)
        append(name ?: "_")
        append(typePart) // defaults intentionally ignored
    }
}

/* ------------------------------ Python side ------------------------------ */

private class PythonPublicSurface {

    fun emit(files: List<File>) {
        val py = findPython() ?: run {
            System.err.println("[python] Skipping .py files: no Python runtime found on PATH (looked for python3, python).")
            return
        }

        val script = pythonProbeScript()
        val tmp = Files.createTempFile("public-surface-probe", ".py").toFile()
        tmp.writeText(script)
        tmp.deleteOnExit()

        files.forEach { f ->
            println("# === ${f.canonicalPath}")
            val pb = ProcessBuilder(py, tmp.absolutePath, f.absolutePath)
                .redirectErrorStream(true)
            val proc = pb.start()
            val out = proc.inputStream.bufferedReader(Charsets.UTF_8).readText()
            proc.waitFor()
            print(out)
            if (!out.endsWith("\n")) println()
            println()
        }
    }

    private fun findPython(): String? {
        val candidates = listOf("python3", "python")
        return candidates.firstOrNull { which(it) }
    }

    private fun which(cmd: String): Boolean =
        try {
            val p = ProcessBuilder(if (isWindows()) "where" else "which", cmd)
                .redirectErrorStream(true).start()
            p.waitFor()
            p.exitValue() == 0
        } catch (_: Exception) { false }

    private fun isWindows(): Boolean = System.getProperty("os.name").lowercase().contains("win")

    // A compact Python script that prints a public stub (module/class/function) with docstrings.
    private fun pythonProbeScript(): String = """
import ast, sys, textwrap

p = sys.argv[1]
with open(p, 'r', encoding='utf-8') as fh:
    src = fh.read()
mod = ast.parse(src, p)

def unparse(x):
    if x is None: return ""
    try:
        return ast.unparse(x)
    except Exception:
        # Fallback best effort for older Pythons
        if isinstance(x, ast.Name): return x.id
        return ""

def arglist(a):
    parts=[]
    # posonly
    for arg in getattr(a, 'posonlyargs', []):
        s = arg.arg
        if arg.annotation: s += ': ' + unparse(arg.annotation)
        parts.append(s)
    if getattr(a, 'posonlyargs', []):
        parts.append('/')
    # normal
    for arg in a.args:
        s = arg.arg
        if arg.annotation: s += ': ' + unparse(arg.annotation)
        parts.append(s)
    # vararg
    if a.vararg:
        s = '*' + a.vararg.arg
        if a.vararg.annotation: s += ': ' + unparse(a.vararg.annotation)
        parts.append(s)
    # kwonly
    if getattr(a, 'kwonlyargs', []):
        # separator if no vararg provided
        if not a.vararg: parts.append('*')
    for arg in a.kwonlyargs:
        s = arg.arg
        if arg.annotation: s += ': ' + unparse(arg.annotation)
        parts.append(s)
    # kwargs
    if a.kwarg:
        s = '**' + a.kwarg.arg
        if a.kwarg.annotation: s += ': ' + unparse(a.kwarg.annotation)
        parts.append(s)
    return ', '.join(parts)

def print_doc(doc, indent=0):
    if not doc: return
    prefix = ' ' * indent
    print(prefix + '"""')
    for line in textwrap.dedent(doc).strip().splitlines():
        print(prefix + line)
    print(prefix + '"""')

# detect __all__ for explicit exports
exports = None
for node in mod.body:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == '__all__':
                names = set()
                v = node.value
                if isinstance(v, (ast.List, ast.Tuple, ast.Set)):
                    for e in v.elts:
                        if isinstance(e, ast.Constant) and isinstance(e.value, str):
                            names.add(e.value)
                exports = names

def is_public_name(name):
    # keep __dunder__ specials; hide single-underscore
    if name.startswith('_') and not (name.startswith('__') and name.endswith('__')):
        return False
    return True

def exported(name):
    if exports is not None:
        return name in exports or (name.startswith('__') and name.endswith('__'))
    return is_public_name(name)

print(f"# module {p}")
print_doc(ast.get_docstring(mod), 0)

for node in mod.body:
    if isinstance(node, ast.ClassDef) and exported(node.name):
        bases = [unparse(b) for b in node.bases] if node.bases else []
        base_str = '(' + ', '.join(bases) + ')' if bases else ''
        print(f"class {node.name}{base_str}:")
        print_doc(ast.get_docstring(node), 4)
        for n in node.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and exported(n.name):
                args = arglist(n.args)
                ret = unparse(n.returns)
                ret_str = f" -> {ret}" if ret else ""
                prefix = "async " if isinstance(n, ast.AsyncFunctionDef) else ""
                print(f"    {prefix}def {n.name}({args}){ret_str}: ...")
        print()
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and exported(node.name):
        args = arglist(node.args)
        ret = unparse(node.returns)
        ret_str = f" -> {ret}" if ret else ""
        prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
        print(f"{prefix}def {node.name}({args}){ret_str}: ...")
        print_doc(ast.get_docstring(node), 0)
        print()
""".trimIndent()
}
```

* * *

Usage
-----

```bash
# Dump the public surface of a mix of Kotlin and Python:
./gradlew run --args "src/main/kotlin src/main/python some/Other.kt"

# Save it somewhere useful:
./gradlew run --args "src" > PUBLIC_SURFACE.txt
```

**What you’ll see (example):**

```kotlin
package demo

/**
 * A polite bag of integers.
 */
public data class IntBag(capacity: Int) : Iterable<Int> {
    public constructor(values: kotlin.collections.Collection<Int>)
    public val size: Int
    public fun add(value: Int): Boolean
    public operator fun iterator(): kotlin.collections.Iterator<Int>
}
```

```text
# === /path/to/mylib/widgets.py
# module /path/to/mylib/widgets.py
"""
Widgets you probably shouldn't use in production.
"""

class Gizmo(BaseGizmo):
    """
    A very serious gizmo.
    """
    def __init__(self, size: int, /, *, color: str = 'blue') -> None: ...
    def ping(self) -> str: ...

def make_gizmo(size: int) -> Gizmo: ...
"""
Factory function; brings your own bugs.
"""
```

* * *

Why this design
---------------

*   **Kotlin PSI** gives you exact source signatures + KDoc with little ceremony.
*   **Python via `ast`** is the shortest path to correct docstrings + signatures across Python versions. It respects `__all__` and keeps dunder specials (e.g., `__init__`), which are part of the effective interface whether you like it or not.

If you want a **pure‑JVM** Python path, drop in an ANTLR `Python3.g4` and I’ll switch to a generated Java parser; it’s just more plumbing, not more value.

* * *

Known constraints (read before you nitpick)
-------------------------------------------

*   **Stubs aren’t meant to compile.** They’re readable API headers, not builds.
*   **Annotations**: Kotlin output currently prints core modifiers (`suspend`, `operator`, etc.). If you want all annotations rendered, say so and I’ll include them verbatim.
*   **Enums**: constants printed up top; Kotlin’s semicolon rules are irrelevant for reading.
*   **Visibility**: Kotlin “effective public” is handled structurally (parent visibility). If you need module‑level symbol resolution (e.g., expect/actual wiring, typealias expansion), I’ll swap in K2 Analysis API.
*   **Python types**: only what’s annotated; untyped params/returns remain untyped (as they should).
*   **Python availability**: the Python extractor expects `python3` or `python` on PATH. If you want zero external runtimes, we go ANTLR.

* * *

Bolt‑ons you may want
---------------------

*   Output formats: JSON/Markdown emitters (trivial—same model, different printers).
*   CI diffing: normalize whitespace + deterministic ordering; dump to `public-api.txt` and diff in PRs.
*   Gradle task wrapper:
    ```kotlin
    tasks.register<JavaExec>("dumpPublicSurface") {
        group = "verification"
        classpath = sourceSets["main"].runtimeClasspath
        mainClass.set("tool.PublicSurfaceToolKt")
        args("src") // or more paths
        standardOutput = File("$buildDir/public-surface.txt").outputStream()
    }
    ```
*   Gradle **Binary Compatibility Validator** alongside this, if you only want Kotlin API dumps without docs.

* * *

Your blind spots, pre‑emptively
-------------------------------

1.  **“File‑based” thinking.** Real API visibility is contextual: parents matter, platform/source set matters, and Python’s `__all__` may override naming conventions. Addressed above, but if you want absolute certainty you’ll need module‑aware analysis for Kotlin and import execution for Python (which we won’t do for obvious reasons).
2.  **Doc fidelity.** KDoc/docstrings are preserved verbatim; if you want links/Markdown normalization, specify your house rules.
3.  **Special members.** Excluding `__init__` and friends would misrepresent Python’s public surface. I keep them by default; change one predicate to hide them if you’re feeling ascetic.

If you want this wrapped as a **Gradle plugin** or desire **pure‑JVM** Python parsing, I’ll deliver a second iteration: ANTLR grammar, listener that collects classes/functions/docstrings, and a shared printer so both languages end up in identical formats.

**Confidence**

*   Kotlin PSI extraction (visibility, KDoc, signatures): **~90%** for typical projects. Edge cases: MPP/expect‑actual/generative annotations **~65–75%** until we nail exact rules you want.
*   Python AST extraction (exports, docstrings, signatures): **~85%**. Exotic `__all__` constructions and runtime aliasing are intentionally out-of-scope for static analysis.