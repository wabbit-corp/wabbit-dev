Developing a **shared JVM library** that spans multiple languages requires careful Gradle setup and consideration of interoperability and packaging. This guide will show how to integrate **JRuby (Ruby), Jython (Python), Clojure, Kotlin, Java, and Scala** into a single Gradle build using the Kotlin DSL (`build.gradle.kts`). We’ll also discuss common cross-language issues and strategies to package the result either as one **fat JAR** or as language-specific packages (e.g. a Ruby gem or Python wheel).

Gradle Configuration for a Multi-language Project
-------------------------------------------------

Gradle’s plugin system allows adding support for multiple JVM languages in one project[discuss.gradle.org](https://discuss.gradle.org/t/multiple-language-plugins-for-one-project-is-it-supported-e-g-java-scala/3569#:~:text=Multiple%20language%20plugins%20for%20one,any%20issues%20on%20Gradle%27s%20side). We can apply the necessary plugins and configure source sets and dependencies for each language. Below is a breakdown:

*   **Apply language plugins:** Use the Gradle plugins for each language. For example, apply the Java plugin (or `java-library`), Kotlin JVM plugin, Scala plugin, Clojure plugin, JRuby plugin, and Jython plugin. In Kotlin DSL, this is done in the `plugins { ... }` block, specifying plugin IDs and versions when required. For instance:
    
    ```kotlin
    plugins {
        id("java-library")                     // Java support
        id("org.jetbrains.kotlin.jvm") version "1.9.0"   // Kotlin support
        id("scala")                            // Scala support (built-in)
        id("dev.clojurephant.clojure") version "0.5.0-alpha.1" // Clojure support
        id("com.github.jruby-gradle.base") version "2.1.0-alpha.2" // JRuby support
        id("com.github.jruby-gradle.jar") version "2.1.0-alpha.1"  // JRuby Jar packaging
        id("com.github.hierynomus.jython") version "0.11.0"       // Jython support
    }
    ```
    
    _Gradle fully supports using multiple language plugins in one project_[discuss.gradle.org](https://discuss.gradle.org/t/multiple-language-plugins-for-one-project-is-it-supported-e-g-java-scala/3569#:~:text=Multiple%20language%20plugins%20for%20one,any%20issues%20on%20Gradle%27s%20side). The Kotlin and Scala plugins will introduce their own compile tasks (e.g. `compileKotlin`, `compileScala`) in addition to `compileJava`. The Clojurephant plugin (`dev.clojurephant.clojure`) adds Clojure compilation tasks. The JRuby and Jython plugins provide tasks for handling Ruby and Python resources respectively.
    
*   **Project structure (source sets):** By convention, put source code for each language in separate directories under `src/main`. Gradle recognizes the standard locations for Java (`src/main/java`), Kotlin (`src/main/kotlin`), and Scala (`src/main/scala`). For Clojure, the Clojurephant plugin expects Clojure code in `src/main/clojure` by default. Similarly, the JRuby plugin treats `src/main/ruby` as the Ruby source directory, and for Jython you can use `src/main/python` (the Jython plugin will bundle Python files from the Jython configuration or you can treat them as resources). Keeping code in distinct folders helps each compiler find the correct files.
    
*   **Repositories for dependencies:** Since we are using multiple ecosystems, we need to declare where to fetch dependencies:
    
    *   Use Maven Central (and JCenter if needed) for Java, Kotlin, Scala, and Clojure artifacts.
        
    *   Add Clojars (the Clojure community repository) for Clojure libraries if needed (the Clojure plugin itself is on Gradle Portal, but Clojure libraries like `org.clojure:clojure` or others might be on Maven Central or Clojars). For example:
        
        ```kotlin
        repositories {
            mavenCentral()
            maven("https://repo.clojars.org/")  // Clojars for Clojure libs:contentReference[oaicite:2]{index=2}
            // ... (Gradle Plugin Portal is used internally for plugins)
        }
        ```
        
    *   Add RubyGems as a repository for JRuby gem dependencies. The JRuby Gradle plugin provides a way to resolve RubyGems. In Groovy DSL one could do `repositories { rubygems() }`. In Kotlin DSL, we must access the extension for RubyGems. For example:
        
        ```kotlin
        import com.github.jrubygradle.api.core.RepositoryHandlerExtension
        (repositories as org.gradle.api.plugins.ExtensionAware)
            .extensions.configure<RepositoryHandlerExtension>(repositories) {
                gems()  // enable RubyGems repository
            }
        ```
        
        This makes Ruby gems resolvable via Gradle[github.com](https://github.com/jruby-gradle/jruby-gradle-plugin/issues/407#:~:text=import%20com).
        
    *   The Jython plugin by Hierynomus automatically knows how to fetch packages from PyPI (Python Package Index) when we declare `jython` dependencies (it defines its own repository pattern for pip)[github.com](https://github.com/hierynomus/jython-gradle-plugin#:~:text=By%20default%20the%20following%20two,been%20defined%20for%20the%20plugin). We typically don’t need to add PyPI manually; the plugin does REST calls to PyPI to download packages[github.com](https://github.com/hierynomus/jython-gradle-plugin#:~:text=).
        
*   **Dependencies for each language:** Add the necessary runtime libraries and any language-specific dependencies:
    
    *   **Java/Scala/Kotlin:** These languages compile to class files directly. Ensure the Scala standard library is included (the Scala plugin does _not_ automatically add it). For example:
        
        ```kotlin
        dependencies {
            implementation("org.scala-lang:scala-library:2.13.11")  // Scala runtime library
            implementation(kotlin("stdlib"))  // Kotlin standard library
            // Java has no extra runtime dependency beyond the JDK
        }
        ```
        
        The Kotlin plugin will handle Kotlin reflection or stdlib if needed, but explicitly adding `kotlin("stdlib")` is a good practice. For Scala, choose a version compatible with your code. The Java and Kotlin plugins integrate naturally (Kotlin can call Java classes and vice versa), and Gradle will coordinate their compilation. Scala and Java also integrate (Gradle runs the Scala compiler which can also compile any Java sources for cross-language references). **Note:** Mixing Scala and Kotlin in the _same module_ can be tricky – if needed, consider separate subprojects for Scala and Kotlin sources[users.scala-lang.org](https://users.scala-lang.org/t/build-systems-for-scala/10227#:~:text=Build%20Systems%20for%20Scala%20,support%20soon%2C%20and%20sbt) to avoid compiler order issues.
        
    *   **Clojure:** Add the Clojure runtime as a dependency. Typically, include the same version of Clojure that you use to write the code. For example:
        
        ```kotlin
        dependencies {
            implementation("org.clojure:clojure:1.11.1")    // Clojure language runtime:contentReference[oaicite:7]{index=7}
        }
        ```
        
        The Clojurephant plugin will compile Clojure source files. By default it may only compile namespaces that are _explicitly_ AOT (ahead-of-time) compiled or needed for certain tasks. You can configure AOT compilation if you want `.class` files for your Clojure code (more on this later). In build.gradle.kts, one can do:
        
        ```kotlin
        clojure {
            builds {
                named("main") {
                    aotAll()  // compile all Clojure namespaces ahead-of-time
                }
            }
        }
        ```
        
        This ensures Clojure produces `.class` files for all namespaces in `src/main/clojure`, which is useful for generating Java-callable classes or speeding up startup[clojure.org](https://clojure.org/compilation#:~:text=Clojure%20compiles%20all%20code%20you,to%20use%20AOT%20compilation%20are).
        
    *   **JRuby (Ruby on JVM):** Include the JRuby engine and any Ruby gems needed:
        
        *   Add JRuby’s engine JAR. You have two options: **jruby-core** (engine without stdlib) or **jruby-complete** (engine + Ruby standard libraries). Using jruby-complete is simplest if you want a self-contained jar. For example,
            
            ```kotlin
            dependencies {
                implementation("org.jruby:jruby-complete:9.4.2.0")  // JRuby engine
            }
            ```
            
            (JRuby 9.4.x corresponds to Ruby 3.1 compatibility). The JRuby Gradle plugin might bring a default JRuby version, but explicitly including ensures the version.
            
        *   Declare Ruby gem dependencies via Gradle if needed. The JRuby plugin allows specifying gem coordinates as Gradle dependencies once RubyGems repo is enabled. For example, to include a Ruby gem `some_gem` version `1.0`:
            
            ```kotlin
            dependencies {
                implementation("rubygems:some_gem:1.0")
            }
            ```
            
            In older JRuby Gradle versions, a special configuration `gems` was used: e.g. `dependencies { gems "rubygems:asciidoctor-diagram:1.5.19" }`[stackoverflow.com](https://stackoverflow.com/questions/79205794/gradle-dsl-ruby-gems-build-fails#:~:text=dependencies%20%7B%20gems%20%27rubygems%3Aasciidoctor). In current JRuby/Gradle, using the `implementation` configuration with the `rubygems:` coordinate works similarly (the plugin sets up a Rubygems Maven proxy[github.com](https://github.com/jruby-gradle/jruby-gradle-plugin/issues/407#:~:text=The%20way%20this%20plugin%20configures,nice%20with%20the%20Kotlin%20DSL)).
            
        *   Place your Ruby source files under `src/main/ruby`. The JRuby Jar plugin (`com.github.jruby-gradle.jar`) will package these `.rb` files into the output JAR and ensure they can be executed via the JRuby runtime. You can also write JRuby code that will be pre-compiled or invoked at runtime (more on this under interoperability).
            
    *   **Jython (Python on JVM):** Include the Jython engine and Python libraries:
        
        *   Add Jython’s standalone JAR to run Python code on the JVM. For example:
            
            ```kotlin
            dependencies {
                implementation("org.python:jython-standalone:2.7.4")  // Jython 2.7.x
            }
            ```
            
            (Jython 2.7.4 is the latest stable supporting Python 2.7 syntax). This allows running Python code via Jython.
            
        *   Use the Jython Gradle plugin to fetch Python packages from PyPI if your project depends on any. The plugin introduces a custom dependency notation. For example:
            
            ```kotlin
            dependencies {
                jython(":boto3:1.1.3")
            }
            ```
            
            This will download the **boto3** Python library version 1.1.3 from PyPI and bundle it into the jar[github.com](https://github.com/hierynomus/jython-gradle-plugin#:~:text=The%20following%20example%20will%20download,it%20in%20your%20Jar%20file). The string format `":package:version"` (with an empty group) signals the plugin to use PyPI. You can also use the `python("name:artifact:version")` DSL for more control (e.g. specifying module names)[github.com](https://github.com/hierynomus/jython-gradle-plugin#:~:text=In%20some%20cases%2C%20the%20python,accordingly). The plugin will package these Python modules so they can be used at runtime.
            
        *   Place any of your own Python scripts in a directory (e.g. `src/main/python`). Jython can load `.py` files from the classpath, so bundling them in the jar as resources is sufficient. Ensure they are included (you might add `resources.srcDir("src/main/python")` in Gradle if needed, or treat them as part of the Jython plugin’s processing).
            

With these configurations, running Gradle will compile all languages. For example, `gradle compileKotlin compileJava compileScala compileClojure` will produce `.class` files from Kotlin, Java, Scala, and Clojure; JRuby and Jython don’t produce class files for scripts, but their files will be packaged. **Gradle’s Kotlin DSL** is fully supported, though certain plugin specifics (like adding the RubyGems repo) require using the extension APIs as shown above.

Common Language Interoperability Issues and Solutions
-----------------------------------------------------

Combining languages means components written in one language will need to interact with components in another. The JVM provides a common platform (Java bytecode), but differences in language paradigms can raise issues. Here are common challenges and how to address them:

*   **Type and API compatibility:** Each language has its own type system and standard library. When calling code across languages, be mindful of data types:
    
    *   **Java <-> Kotlin/Scala:** These are statically typed and have very good interop. Kotlin and Scala classes are compiled to Java-compatible classes. For example, Kotlin’s classes can be used in Java as normal (though Kotlin’s nullability is enforced only at compile-time in Kotlin). Scala’s classes (especially case classes or collections) can be used in Java, but some idioms (e.g. Scala’s `Option`) may need conversion to Java `Optional` manually. Conversely, Java classes are accessible in Kotlin and Scala without special effort. You may just need to add annotations or adapters if you want to idiomatically handle things like Java’s `Optional` in Scala or Kotlin.
        
    *   **Java/Kotlin/Scala <-> Clojure:** Clojure is dynamic and data-oriented. Calling Java-based code from Clojure is straightforward – Clojure has built-in Java interop syntax. For example, you call instance methods with `(.methodName object args...)` and static methods with `(ClassName/staticMethod args...)`. Clojure collections (lists, vectors, maps) implement Java interfaces (e.g. Clojure’s persistent vectors implement `java.util.List`), so you can pass them to Java methods expecting those interfaces. When **Java (or Kotlin/Scala) calls Clojure** code, it’s trickier: Clojure functions live in namespaces and by default are invoked through the Clojure runtime. One approach is **ahead-of-time (AOT) compiling** Clojure to generate Java classes. Clojure’s `gen-class` facility allows you to define a class in Clojure that implements interfaces or extends a Java class, exposing Clojure functions as true Java methods[clojure.org](https://clojure.org/compilation#:~:text=Clojure%20compiles%20all%20code%20you,to%20use%20AOT%20compilation%20are)[clojure.org](https://clojure.org/compilation#:~:text=,startup). For example, you could write a Clojure namespace with `(ns mylib.core (:gen-class ...))` and implement, say, a `public void invoke()` method. After AOT compile (which we enabled with `aotAll()` or could do per namespace), you’ll have a `.class` that Java can call directly. If you don’t want to AOT, an alternative is using Clojure’s runtime API: Java code can call `clojure.java.api.Clojure.var("myns", "my-fn").invoke(args...)` to invoke a function dynamically. This requires the Clojure runtime to be initialized (which happens if you included Clojure as a dependency). In summary, to make Java↔Clojure interop easier:
        
        *   Use AOT and `gen-class` for Clojure code that needs to be consumed by Java statically (this gives you named classes/interfaces as needed).
            
        *   Use Clojure’s Java interop for Clojure->Java calls (which is idiomatic and performant, especially if type hints are added to avoid reflection).
            
        *   Use the Clojure Java API or `IFn` interface for dynamic invocation if avoiding AOT. (Any Clojure function object implements `clojure.lang.IFn` with an `invoke` method overload.)
            
*   **Java/Kotlin/Scala <-> JRuby (Ruby):** JRuby runs Ruby code on the JVM. **Calling Java from Ruby** is supported out-of-the-box in JRuby. You can import Java classes or packages in Ruby using `include_package` or the `Java::` module. For example, in a JRuby script:
    
    ```ruby
    include Java
    import java.time.LocalDateTime
    puts LocalDateTime.now  # uses a Java class from Ruby
    ```
    
    JRuby will automatically map Java objects to Ruby proxies. Conversely, **calling Ruby from Java/Kotlin** requires an embedded JRuby runtime unless you have precompiled Ruby classes:
    
    *   _Dynamic invocation:_ Use the JSR 223 scripting API (Java’s standard way to run scripts). JRuby provides a `ScriptEngine` implementation. For example, in Java or Kotlin you can do:
        
        ```java
        ScriptEngineManager mgr = new ScriptEngineManager();
        ScriptEngine jrubyEngine = mgr.getEngineByName("jruby");
        jrubyEngine.eval("require 'mylibrary'"); 
        jrubyEngine.eval("MyRubyModule.do_something(123)");
        ```
        
        This evaluates Ruby code within a JRuby engine[nts.strzibny.name](https://nts.strzibny.name/using-ruby-gems-in-javagradle-projects-jruby/#:~:text=public%20class%20Main%20,jruby)[nts.strzibny.name](https://nts.strzibny.name/using-ruby-gems-in-javagradle-projects-jruby/#:~:text=rubyEngine.eval%28%20,amount%3A%20%27%24%20900%27%5Cn). Kotlin can use the same classes from `javax.script`. This approach is useful for calling into Ruby on the fly. It requires your Ruby code (and any gems) to be available on the classpath or loadable by JRuby (our Gradle setup ensures the Ruby files are packaged, and using `jrubyEngine.eval("require 'file.rb'")` can load them).
        
    *   _Compile Ruby to Java class:_ JRuby has an **ahead-of-time compiler** (the `jrubyc` tool) that can turn Ruby scripts into `.class` files. This is less commonly used, but it can generate Java bytecode for Ruby code. However, even compiled Ruby classes still depend on the JRuby runtime library. A more typical pattern is to write a Ruby class that **implements a Java interface or extends a Java class** so that it can be called from Java naturally. JRuby allows Ruby classes to implement Java interfaces simply by subclassing them. For example, if you have a Java interface `com.example.Task`, you can implement it in Ruby:
        
        ```ruby
        java_package 'com.example'
        class RubyTask < Java::com.example.Task
          def initialize; end
          def execute() 
            puts "Task executed"
          end
        end
        ```
        
        Now `RubyTask` is a Java class (under the package `com.example`) that implements `Task`. Java code could do `Task t = new RubyTask(); t.execute();` thanks to JRuby’s integration. Internally, JRuby creates a proxy class. This technique is powerful but requires the JRuby runtime present at runtime (which we have as a dependency). If creating such classes at runtime is inconvenient, you could AOT compile them.
        
        For simpler needs, using the scripting API or JRuby’s **JVM integration APIs** (`org.jruby.RubyInstanceConfig` and `org.jruby.embed.LocalVariableBehavior` etc.) lets you call Ruby code and retrieve results as Java types.
        
    *   **Data conversion:** JRuby will try to convert basic types between Ruby and Java (e.g. Ruby strings to `java.lang.String` when calling a Java method, or Java collections to Ruby `Array` when accessed in Ruby). You may sometimes need to manually convert types or use JRuby’s helper methods (`to_java` / `to_a` etc.) to get the desired types.
        
*   **Java/Kotlin/Scala <-> Jython (Python):** Jython is similar to JRuby in that Python code runs on the JVM. **Java from Python**: Jython allows using any Java class directly in Python code (just like in JRuby). In a Jython script, you can do:
    
    ```python
    from java.util import Date
    d = Date()  # create Java Date in Python
    print(d.getTime())
    ```
    
    Jython will handle conversion of primitive types seamlessly. **Calling Python from Java/Kotlin** is again a matter of embedding the interpreter or precompiling:
    
    *   Use JSR 223 scripting: Jython provides a `ScriptEngine` named “python”. You can load and execute Python code similarly:
        
        ```java
        ScriptEngine pyEngine = mgr.getEngineByName("python");
        pyEngine.eval("import mymodule"); 
        pyEngine.eval("result = mymodule.some_function(42)");
        Object result = pyEngine.get("result");
        ```
        
        This will run the Python code and you can fetch variables back. The result will be a Jython PyObject or a Java object depending on type.
        
    *   Another approach is using the Jython-specific API: `org.python.util.PythonInterpreter`. You can instantiate a `PythonInterpreter` in Java, execute scripts, and use `interp.get()` to retrieve variables.
        
    *   **Implementing interfaces in Python:** Like JRuby, Jython can implement Java interfaces in pure Python code[faculty.kutztown.edu](https://faculty.kutztown.edu/parson/pubs/JythonPACISE2011Talk.pdf#:~:text=Systems%20faculty,Jython%20can%20extend%20Java%20classes). If you define a Python class inheriting from a Java interface, Jython will create a compliant class. For example:
        
        ```python
        from java.lang import Runnable
        class PyTask(Runnable):
            def run(self):
                print("Task from Python")
        ```
        
        Now any Java method expecting a `java.lang.Runnable` can be passed an instance of `PyTask` (Jython will handle the proxying). One caution: Jython may not enforce interface method signatures at _compile_ time (because Python is dynamic), so you must ensure the methods are defined correctly to avoid runtime errors[stackoverflow.com](https://stackoverflow.com/questions/60637340/why-does-jython-not-enforce-the-interface-requirements-of-a-java-interface#:~:text=Why%20does%20Jython%20not%20enforce,when%20I%20made%20an)[faculty.kutztown.edu](https://faculty.kutztown.edu/parson/pubs/JythonPACISE2011Talk.pdf#:~:text=Systems%20faculty,Jython%20can%20extend%20Java%20classes).
        
    *   If you want to avoid the interpreter overhead each time, Jython had a tool called **jythonc** (in older versions) that could compile Python to Java classes. In modern Jython 2.7.x, jythonc is deprecated, so the recommended approach is either dynamic invocation or writing Java-callable wrappers (like the interface implementation above).
        
    *   **Data conversion:** Jython’s objects (e.g. `PyString`, `PyList`) often subclass or are convertible to Java equivalents. For instance, Jython’s `PyList` implements `java.util.List` so you can pass it to Java directly[faculty.kutztown.edu](https://faculty.kutztown.edu/parson/pubs/JythonPACISE2011Talk.pdf#:~:text=Systems%20faculty,Jython%20can%20extend%20Java%20classes). Primitive types and strings usually auto-convert. If a Java API returns a collection, Jython may present it as a Python list via integration.
        
*   **Clojure <-> JRuby/Jython (Dynamic <-> Dynamic):** Direct interaction between, say, Ruby and Clojure code on the JVM is less common, but possible since all share the JVM. Typically, they would communicate via Java interfaces or classes as an intermediary. For example, you might have a Java interface that both a Clojure class (via gen-class) and a JRuby class implement; then they can be used interchangeably by Java code. Without an interface, one dynamic language can still call the other by going through Java: e.g., JRuby can call Clojure by using the Clojure Java API to invoke a function, or Clojure can call JRuby by using the JRuby embed API. These are advanced scenarios – a simpler approach is to refactor shared logic into Java/Kotlin (which both Ruby and Clojure can call easily) if you find yourself needing a lot of cross-calling between dynamic languages.
    
*   **Threading and state:** All these languages run on the JVM, so threads and memory are shared. If you have mutable state, be mindful of thread safety across languages. For example, a Java thread might call a Clojure function – that function might internally use Clojure’s STM or other concurrency primitives which are thread-safe, but if sharing data, ensure any concurrency primitives are respected across languages. In general, Java’s synchronization locks are usable by any JVM language (a Ruby `synchronized {}` block or a Python `with threading.Lock():` will ultimately use JVM locks). Garbage collection is unified on the JVM, so you don’t need to manage separate GCs, but finalization or resource management might differ (Clojure relies on Java GC, JRuby/Jython also rely on JVM GC for memory but have their own heap for objects). Usually these differences do not require special action, just be aware that (for example) JRuby’s objects are garbage-collected by the JVM like any Java object.
    
*   **Exception handling:** Exceptions can be tricky cross-language. A Java exception thrown will bubble through Clojure or JRuby code as a Java exception (JRuby will wrap it in a Ruby `RuntimeError` if not caught in Ruby, but if not caught at all it can be seen as a Java exception too). Similarly, if a JRuby script throws a Ruby exception and it isn’t caught, when it propagates to Java it will typically be an instance of `org.jruby.exceptions.RaiseException` (with the Ruby traceback inside). You may need to catch the language-specific exception classes in Java, or catch a general `Exception` and inspect cause. The key is to decide which side to handle errors on – often it’s easiest to catch and translate exceptions at the boundary (e.g., catch a Python exception in Jython and throw a Java exception with the message for the Java code).
    

**Making interactions easier or more idiomatic:**

*   Define clear **interfaces or abstract classes** in Java that serve as contracts between languages. This way, dynamic languages can implement those interfaces (as shown for JRuby/Jython), and static languages can call them without worrying about the implementation details. This is a common pattern to keep things modular.
    
*   Use each language for what it’s best at, and call across when needed, but avoid overly chatty cross-language calls. Each cross-language call may incur conversion overhead (e.g., converting a large data structure from a Clojure persistent map to a Java `HashMap` or to a JRuby hash could be expensive). If heavy data manipulation is needed, consider doing it on one side and only passing final results across.
    
*   When designing API, consider providing thin idiomatic wrappers in each language:
    
    *   For example, your core logic might be in Java, but you could write a small Clojure namespace with functions that call the Java static methods in a way that feels natural to Clojure users (accepting Clojure data structures, converting to Java, calling the Java code, then converting results back to Clojure types).
        
    *   For JRuby, you might provide a Ruby module that wraps around the Java classes or calls, so Ruby users can call a Ruby-style method which under the hood invokes the Java logic. (JRuby makes it easy to call Java, but a wrapper can hide Javaisms and provide a more Ruby-like API).
        
    *   For Jython/Python, similarly, a pure Python module can wrap Java calls (e.g., providing a Python function instead of requiring the user to interact with Java classes directly).
        
*   **Documentation and examples** are important: show how to use the final library from each language. For instance, demonstrate how a Scala developer would use it (probably just adding the JAR and calling the classes), how a Clojure developer would use it (perhaps by requiring the Clojure namespace or interop with Java classes), how a JRuby user would require the gem, etc. Making usage frictionless in each language’s ecosystem is key to an idiomatic experience.
    

Packaging the Polyglot Library
------------------------------

After building the project, packaging and distributing it in a convenient form is crucial. We have two broad approaches:

1.  **Single fat JAR distribution**, containing all code and dependencies (except perhaps language runtimes if not desired).
    
2.  **Modular, Maven-published artifacts** for each facet, and optionally language-specific packaging (Ruby gems, Python wheels) for dynamic language ecosystems.
    

### 1\. Fat JAR (Uber JAR) Approach

A **fat JAR** bundles everything into one JAR file – your code from all languages plus all required dependency libraries. The result can be a standalone library or even an executable (if you include a main class). In our case, a fat JAR could include the Scala library, Clojure runtime, JRuby engine, Jython engine, and any gems or Python packages used – essentially one file that works anywhere on a JVM.

**How to create a fat JAR in Gradle:** One popular plugin is the Gradle Shadow plugin. You can apply `id("com.github.johnrengelman.shadow") version "7.1.2"` (for example) and then run `gradle shadowJar`. This will produce a `*-all.jar` that contains all project classes and dependencies. If using the Shadow plugin, you might mark some dependencies as provided if you don’t want them included (for example, if you expect JRuby to be provided by the runtime environment, you could exclude it).

However, since we applied the **JRuby Jar plugin**, it already can create an _uberjar_ for JRuby projects. The JRuby Gradle plugin’s `jar` portion will include Ruby code and can also embed the JRuby runtime. In fact, the JRuby Gradle plugin exists to _“build jar files… and much more”_ combining Ruby and Java[github.com](https://github.com/jruby-gradle/jruby-gradle-plugin#:~:text=JRuby%2FGradle%20brings%20the%20power%20and,run%20tests%2C%20and%20much%20more). We would configure it to include the JRuby engine (`jruby-complete`) so that the JAR can run Ruby code standalone. Similarly, the Jython plugin by Hierynomus, when we added `jython` dependencies, ensures those Python libraries (and likely the Jython runtime if on classpath) are bundled in the output JAR[github.com](https://github.com/hierynomus/jython-gradle-plugin#:~:text=The%20following%20example%20will%20download,it%20in%20your%20Jar%20file). So simply running Gradle’s standard `jar` task in this setup may already produce a jar containing:

*   All `.class` files from Java, Kotlin, Scala, Clojure.
    
*   All Ruby `.rb` files (the JRuby plugin will package them, possibly under a path and include a `jruby-core` jar inside if configured).
    
*   All Python `.py` files or extracted packages (the Jython plugin by default unpacks the Python packages into the jar).
    
*   The runtime libraries: JRuby and Jython engines, Clojure, Scala library, etc, if they are listed as implementation dependencies.
    

You will need to ensure that your jar’s **Manifest** has the correct Main-Class if this jar is meant to be executable. The JRuby plugin can create a _self-contained JRuby jar_ with an entry point (e.g., to run a specific Ruby script). If your library is not an application, you might not need a main class.

**Pros of fat JAR:** One file to distribute; easy for Java/Scala developers to drop in and use. It ensures consistent versions of everything. Also, it’s convenient for testing – you know all pieces are present.

**Cons:** Fat JARs can be large (because they include e.g. the entire JRuby stdlib and Jython, which together could be tens of MB). If a user only needs some parts (say they only use the Java API and don’t care about Ruby/Python), they still have the overhead. Also, if distributing to environments that already have those languages, a fat JAR duplicates them (for instance, a JRuby user running on JRuby already has the JRuby runtime – bundling it again in the jar is redundant).

**Shading and conflicts:** If you do a fat jar, you should be mindful of duplicate classes (for example, JRuby and Jython both include some common libraries like ASM for bytecode manipulation or logging libraries – Shadow plugin can relocate packages if necessary to avoid conflicts). Ensure that your fat jar doesn’t have conflicting versions of the same class. In practice, using consistent dependency versions and shading where needed solves this.

### 2\. Modular Maven Artifacts (and Language-specific Packages)

In this approach, we produce a set of artifacts that can be published to appropriate repositories:

*   **JVM artifacts (JARs)**: You might publish a core JAR (with just your compiled classes and maybe resource files from dynamic languages) to Maven Central. This JAR would declare dependencies on needed runtimes rather than include them. For example, your `mylib.jar` can have `org.jruby:jruby-complete` and `org.python:jython-standalone` as Maven dependencies (so users can pull them if needed). You could also split artifacts by language:
    
    *   `mylib-core.jar`: containing the core Java/Scala/Kotlin/Clojure compiled classes.
        
    *   `mylib-ruby.jar`: containing Ruby code and possibly JRuby-specific helper classes (but not the JRuby engine).
        
    *   `mylib-python.jar`: containing Python scripts or wrappers (but not the Jython engine).  
        In many cases, a single jar with everything _except_ the heavy runtime engines is sufficient; JRuby and Jython can be regular dependencies. This keeps the artifact size smaller while still making it easy for any JVM user to include the library. A Java/Scala/Clojure developer would include `mylib` and also get JRuby/Jython on the classpath (if your pom lists them). If they don’t need JRuby/Jython, they could exclude those transitive deps.
        
*   **Ruby Gem (for JRuby users):** To cater to JRuby users in their native workflow, you can package a Ruby gem. There are two strategies:
    
    1.  **Pure-Java gem**: Some JRuby gems include Java bytecode. You can take the core JAR you built and add it into a gem. For example, create a gem structure with:
        
        *   `lib/mylib.jar` (your jar file)
            
        *   `lib/mylib.rb` (a bootstrap Ruby file)
            
        *   `mylib.gemspec`
            
        
        In the gemspec, you can declare a dependency on the `jar-dependencies` gem and list the Maven coordinates of your jar or other jars. The **jar-dependencies** library allows a gem to automatically pull down JAR files from Maven Central when the gem is installed or required[stackoverflow.com](https://stackoverflow.com/questions/35461309/jruby-gemspec-local-jar-dependencies#:~:text=,adapter)[stackoverflow.com](https://stackoverflow.com/questions/35461309/jruby-gemspec-local-jar-dependencies#:~:text=s.requirements%20%3C%3C%20,dependencies). For instance, in the gemspec:
        
        ```ruby
        s.name = "mylib"
        s.version = "1.0"
        s.summary = "My polyglot library"
        s.require_paths = ["lib"]
        s.files = Dir["lib/**/*"] + ["mylib.gemspec"]
        # Declare jar dependencies:
        s.add_runtime_dependency "jar-dependencies", "~> 0.4"
        s.requirements << "jar 'com.mycompany:mylib:1.0'" 
        ```
        
        The above line tells jar-dependencies to fetch the Maven artifact `com.mycompany:mylib:1.0` (which would be the JAR you published to Maven). This way, the gem doesn’t even need to include the jar – it can download the correct version from Maven at runtime[stackoverflow.com](https://stackoverflow.com/questions/35461309/jruby-gemspec-local-jar-dependencies#:~:text=,adapter)[stackoverflow.com](https://stackoverflow.com/questions/35461309/jruby-gemspec-local-jar-dependencies#:~:text=s.requirements%20%3C%3C%20,dependencies). The user experience for JRubyists is: they install the gem, and when they `require 'mylib'`, jar-dependencies will ensure the JAR is on the classpath.
        
        Alternatively, you could **vendor** the jar inside the gem (include `lib/mylib.jar` in the gem files) and then in `lib/mylib.rb`, write:
        
        ```ruby
        require 'java'
        require_relative 'mylib.jar'
        # perhaps load some Ruby integration code or simply let users use the Java API
        ```
        
        This approach doesn’t require downloading from Maven (the jar travels with the gem), but it makes the gem larger. It’s simpler for offline use. You can still use jar-dependencies but point it to a local jar path.
        
        If your library also has Ruby source code (e.g., idiomatic Ruby wrapper methods), include those `.rb` files in the gem’s `lib/` as usual. JRuby will be able to use both the Ruby code and the classes inside the jar.
        
    2.  **JRuby Gradle plugin gem tasks:** The JRuby Gradle plugin primarily focuses on jars and wars, not gem building. There isn’t a built-in “gem assemble” task in the plugin (its goal is more to let Ruby devs use Gradle for jar/war packaging). So building a gem might involve writing a small Rake task or using RubyGems tooling. You could automate gem building in Gradle by invoking JRuby and running `gem build`. For example, using the Gradle JRuby plugin’s exec capabilities:
        
        ```kotlin
        tasks.register("buildGem", Exec::class) {
            dependsOn(jar)  // ensure jar is built
            commandLine("jruby", "-S", "gem", "build", "mylib.gemspec")
        }
        ```
        
        (This assumes JRuby is installed or you use the plugin’s JRubyExec which knows the JRuby in classpath.) This will produce `mylib-1.0.gem` which you can publish to RubyGems.org for JRuby users.
        
    
    Once published, JRuby users can `gem install mylib` and then `require 'mylib'`. Thanks to the packaging, this will load your library. They can then call any Java classes from it, or use any Ruby-friendly API you provided. The gem’s platform can be marked `java` in the gemspec (to indicate it’s only for JRuby). For example: `s.platform = 'java'`.
    
*   **Python Package (for Jython users):** Jython users typically use Python’s packaging. You can create a Python wheel or egg for your library:
    
    *   Write a `setup.py` for your project that includes your Python modules and any Java JARs as package data. For example, include the core JAR in the `package_data` so that it ends up inside the wheel. You might also decide not to include the Jython runtime itself (Jython users will have Jython), but include your library’s jar.
        
    *   In your Python module (e.g., `mylib/__init__.py`), ensure the JAR is added to the classpath. One convenient trick: Jython will scan the `sys.path` for `.jar` files and load them as Java libraries[jython.readthedocs.io](https://jython.readthedocs.io/en/latest/ModulesPackages/#:~:text=Chapter%208%3A%20Modules%20and%20Packages,This%20has%20the). If your jar is installed in the site-packages, you can append its path to `sys.path` at runtime. For instance:
        
        ```python
        import pkg_resources, sys
        jar_path = pkg_resources.resource_filename(__name__, "mylib.jar")
        if jar_path not in sys.path:
            sys.path.append(jar_path)
        ```
        
        This will add the jar from your package to Jython’s classpath dynamically. After that, you can `import com.mycompany.MyClass` or whatever classes directly in Jython.
        
    *   Alternatively, instruct users to put the JAR on Jython’s classpath (less ideal for a Python-first user). The wheel approach makes it seamless – a Jython user can `pip install mylib`, then in their Jython environment do `import mylib` and your initialization code loads the jar.
        
    *   You might also provide a pure-Python API wrapping the Java calls. For example, if your library has a class `com.mycompany.Foo` with method `doThing(int)`, you can in `mylib/__init__.py` write a Python function:
        
        ```python
        from com.mycompany import Foo
        def do_thing(x):
            return Foo.doThing(x)
        ```
        
        So a Jython user calls `mylib.do_thing(5)` and under the hood it calls the Java logic.
        
    *   **Publishing to PyPI:** Use standard Python tooling (setuptools/twine) to upload the wheel. Note that Jython 2.7 corresponds to Python 2 syntax; if you also want to support usage on CPython (maybe your library’s Python API could work on CPython via JPype or similar bridging, but that’s another story), you’d need to maintain Python 3 compatibility separately. Likely, this library is mainly for Jython, so Python 2 syntax is fine.
        
*   **Standard JAR publication:** Use Gradle’s `maven-publish` plugin to publish your JARs to Maven Central (or a company Nexus/Artifactory). You’d create a publication for the main jar and any auxiliary jars (if you split core and -ruby, -python jars). Many organizations keep it simple with one jar. The artifacts should include POM entries for dependencies:
    
    *   E.g. your POM can list `org.jruby:jruby-complete` as a dependency, so if a Java developer uses Maven to add your library, they automatically get JRuby on their classpath (needed if they want the Ruby part to work). If they don’t need it, they can exclude it. This approach offloads the decision to the user.
        
    *   If you published separate modules, you might have `mylib-core` (with no JRuby dependency) and a `mylib-jruby` (that depends on core and on JRuby and includes the Ruby files). A JRuby user could just use the gem in that case, but a Java developer who wants to use the Ruby portion might explicitly add `mylib-jruby`. This modular approach is nice for optional components.
        

**Summary of packaging choices:** For maximum reach:

*   Publish the core JAR to Maven (so Java, Scala, Clojure, Kotlin developers can get it easily).
    
*   Publish a Ruby gem for JRuby users (possibly including or auto-fetching the core JAR).
    
*   Publish a Python wheel for Jython users (including the core JAR).
    

This covers all ecosystems. In practice, JRuby usage in the wild might simply use the Maven coordinates via jar-dependencies (so the gem approach is one way or they could directly use the JAR if they know how). Jython is less common these days (limited to Python 2.7), but enterprise users might appreciate a ready-to-go package.

Tool and Plugin Recommendations
-------------------------------

To implement the above effectively, here’s a quick list of useful tools and documentation:

*   **Gradle plugins:**
    
    *   _Kotlin JVM Plugin:_ Official Kotlin plugin (see Kotlin docs on Gradle setup[kotlinlang.org](https://kotlinlang.org/docs/gradle-configure-project.html#:~:text=Configure%20a%20Gradle%20project%20,and%20configure%20the%20project%27s)).
        
    *   _Scala Plugin:_ Built-in Gradle plugin (Gradle documentation has a sample for Scala and Java in one project[discuss.gradle.org](https://discuss.gradle.org/t/multiple-language-plugins-for-one-project-is-it-supported-e-g-java-scala/3569#:~:text=Multiple%20language%20plugins%20for%20one,any%20issues%20on%20Gradle%27s%20side)).
        
    *   _Clojurephant Plugin:_ Gradle plugin for Clojure. Documentation and guides are available on clojurephant.dev (the Quick Start we cited shows how to add Clojure and Clojars repo[github.com](https://github.com/clojurephant/clojurephant#:~:text=repositories%20,)).
        
    *   _JRuby-Gradle Plugin:_ Plugin by the JRuby community. See the jruby-gradle GitHub for usage. It allows declaring `rubygems:` dependencies and packaging JRuby jars. _(Note:_ When using Kotlin DSL, you may need the ExtensionAware trick to call `gems()` on repositories due to a known issue[github.com](https://github.com/jruby-gradle/jruby-gradle-plugin/issues/407#:~:text=The%20way%20this%20plugin%20configures,nice%20with%20the%20Kotlin%20DSL).)
        
    *   _Jython Gradle Plugin:_ Available on Gradle Plugin Portal as `com.github.hierynomus.jython`. The README on GitHub shows examples of dependency notation and configuration[github.com](https://github.com/hierynomus/jython-gradle-plugin#:~:text=The%20following%20example%20will%20download,it%20in%20your%20Jar%20file).
        
    *   _Shadow Plugin:_ For fat jar creation, if not relying on jruby-gradle’s jar task.
        
    *   _Maven Publish Plugin:_ To publish jars to Maven Central.
        
*   **Language documentation:**
    
    *   _Clojure AOT and gen-class:_ Official Clojure documentation on compilation[clojure.org](https://clojure.org/compilation#:~:text=Clojure%20compiles%20all%20code%20you,to%20use%20AOT%20compilation%20are) and the `gen-class` function (useful for interop).
        
    *   _JRuby documentation:_ The JRuby Wiki has info on embedding JRuby and calling Java from Ruby. The JRuby org blog posts can be helpful for examples.
        
    *   _Jython documentation:_ The older “Definitive Guide to Jython” (especially chapters on Jython and Java integration) covers implementing interfaces and using Jython in Java applications[faculty.kutztown.edu](https://faculty.kutztown.edu/parson/pubs/JythonPACISE2011Talk.pdf#:~:text=Systems%20faculty,Jython%20can%20extend%20Java%20classes).
        
    *   _Jar-dependencies gem:_ The README in the jar-dependencies project explains how gems can declare Maven jars[stackoverflow.com](https://stackoverflow.com/questions/35461309/jruby-gemspec-local-jar-dependencies#:~:text=,adapter). If you plan to use that in your gemspec, it’s good to read their guidelines (e.g., all jars must come from Maven Central by default[github.com](https://github.com/jruby/jar-dependencies#:~:text=JARs%20other%20than%20from%20maven)).
        
*   **Community examples:** Look at projects that have done multi-language packaging. For instance, the AsciidoctorJ project uses JRuby under the hood but provides a Java API – their build might offer insight (they use AsciidoctorJ as a jar and also have a gem for Asciidoctor Ruby). Another example: see how Apache Beam or other cross-language systems package things (though those often use separate adapters).
    

Conclusion
----------

Building a polyglot library on the JVM is certainly challenging, but Gradle’s support for multiple languages makes it feasible to organize one project with all source code. By applying the right plugins and following language-specific conventions, you can compile everything together[discuss.gradle.org](https://discuss.gradle.org/t/multiple-language-plugins-for-one-project-is-it-supported-e-g-java-scala/3569#:~:text=Multiple%20language%20plugins%20for%20one,any%20issues%20on%20Gradle%27s%20side). Interoperability requires designing clear boundaries – often using Java interfaces or making use of each language’s ability to call into Java – but as we saw, each pairing has known solutions (from Clojure’s AOT for Java usage[clojure.org](https://clojure.org/compilation#:~:text=Clojure%20compiles%20all%20code%20you,to%20use%20AOT%20compilation%20are), to dynamic languages implementing interfaces for callback patterns[faculty.kutztown.edu](https://faculty.kutztown.edu/parson/pubs/JythonPACISE2011Talk.pdf#:~:text=Systems%20faculty,Jython%20can%20extend%20Java%20classes), to using the JSR223 scripting API for on-the-fly calls). Finally, packaging is about meeting developers where they are: a Java developer will prefer a Maven dependency (or one fat jar), a Ruby developer will appreciate a gem that just works, and a Python developer using Jython will expect a pip-installable package. By producing both a fat JAR **and** ecosystem-specific packages, you maximize usability.

With this approach, you can write components of your library in the language that suits each task best (e.g. use Clojure for flexible data transformation, use Kotlin/Java for performance-critical parts, maybe use Ruby/Python for simple scripting or DSLs), and deliver a cohesive library. Gradle handles the heavy lifting of compilation and assembly, allowing you to focus on making the languages play nicely together.

**Sources:**

1.  Gradle Forum – Confirming multi-language plugin support[discuss.gradle.org](https://discuss.gradle.org/t/multiple-language-plugins-for-one-project-is-it-supported-e-g-java-scala/3569#:~:text=Multiple%20language%20plugins%20for%20one,any%20issues%20on%20Gradle%27s%20side)
    
2.  Clojurephant (Gradle Clojure) usage example – adding Clojure and Clojars[github.com](https://github.com/clojurephant/clojurephant#:~:text=repositories%20,)
    
3.  Stack Overflow – Gradle gem dependency example using JRuby plugin[stackoverflow.com](https://stackoverflow.com/questions/79205794/gradle-dsl-ruby-gems-build-fails#:~:text=dependencies%20%7B%20gems%20%27rubygems%3Aasciidoctor)
    
4.  Hierynomus Jython Gradle Plugin – Example of bundling a PyPI package[github.com](https://github.com/hierynomus/jython-gradle-plugin#:~:text=The%20following%20example%20will%20download,it%20in%20your%20Jar%20file)
    
5.  Clojure.org – Importance of AOT for generating Java-usable classes[clojure.org](https://clojure.org/compilation#:~:text=Clojure%20compiles%20all%20code%20you,to%20use%20AOT%20compilation%20are)
    
6.  Jython integration PDF – Jython can extend Java classes/interfaces[faculty.kutztown.edu](https://faculty.kutztown.edu/parson/pubs/JythonPACISE2011Talk.pdf#:~:text=Systems%20faculty,Jython%20can%20extend%20Java%20classes)
    
7.  Stack Overflow – JRuby gemspec declaring Maven jar dependencies[stackoverflow.com](https://stackoverflow.com/questions/35461309/jruby-gemspec-local-jar-dependencies#:~:text=,adapter)

## Prompt:
Building Polyglot JVM Libraries with Gradle Kotlin DSL

Building a Polyglot JVM Library with Gradle (JRuby, Jython, Clojure, Kotlin, Java, Scala)
=========================================================================================

Developing a **shared JVM library** that spans multiple languages requires careful Gradle setup and consideration of interoperability and packaging. This guide will show how to integrate **JRuby (Ruby), Jython (Python), Clojure, Kotlin, Java, and Scala** into a single Gradle build using the Kotlin DSL (`build.gradle.kts`). We’ll also discuss common cross-language issues and strategies to package the result either as one **fat JAR** or as language-specific packages (e.g. a Ruby gem or Python wheel).

Gradle Configuration for a Multi-language Project
-------------------------------------------------

Gradle’s plugin system allows adding support for multiple JVM languages in one project[discuss.gradle.org](https://discuss.gradle.org/t/multiple-language-plugins-for-one-project-is-it-supported-e-g-java-scala/3569#:~:text=Multiple%20language%20plugins%20for%20one,any%20issues%20on%20Gradle%27s%20side). We can apply the necessary plugins and configure source sets and dependencies for each language. Below is a breakdown:

*   **Apply language plugins:** Use the Gradle plugins for each language. For example, apply the Java plugin (or `java-library`), Kotlin JVM plugin, Scala plugin, Clojure plugin, JRuby plugin, and Jython plugin. In Kotlin DSL, this is done in the `plugins { ... }` block, specifying plugin IDs and versions when required. For instance:
    
    ```kotlin
    plugins {
        id("java-library")                     // Java support
        id("org.jetbrains.kotlin.jvm") version "1.9.0"   // Kotlin support
        id("scala")                            // Scala support (built-in)
        id("dev.clojurephant.clojure") version "0.5.0-alpha.1" // Clojure support
        id("com.github.jruby-gradle.base") version "2.1.0-alpha.2" // JRuby support
        id("com.github.jruby-gradle.jar") version "2.1.0-alpha.1"  // JRuby Jar packaging
        id("com.github.hierynomus.jython") version "0.11.0"       // Jython support
    }
    ```
    
    _Gradle fully supports using multiple language plugins in one project_[discuss.gradle.org](https://discuss.gradle.org/t/multiple-language-plugins-for-one-project-is-it-supported-e-g-java-scala/3569#:~:text=Multiple%20language%20plugins%20for%20one,any%20issues%20on%20Gradle%27s%20side). The Kotlin and Scala plugins will introduce their own compile tasks (e.g. `compileKotlin`, `compileScala`) in addition to `compileJava`. The Clojurephant plugin (`dev.clojurephant.clojure`) adds Clojure compilation tasks. The JRuby and Jython plugins provide tasks for handling Ruby and Python resources respectively.
    
*   **Project structure (source sets):** By convention, put source code for each language in separate directories under `src/main`. Gradle recognizes the standard locations for Java (`src/main/java`), Kotlin (`src/main/kotlin`), and Scala (`src/main/scala`). For Clojure, the Clojurephant plugin expects Clojure code in `src/main/clojure` by default. Similarly, the JRuby plugin treats `src/main/ruby` as the Ruby source directory, and for Jython you can use `src/main/python` (the Jython plugin will bundle Python files from the Jython configuration or you can treat them as resources). Keeping code in distinct folders helps each compiler find the correct files.
    
*   **Repositories for dependencies:** Since we are using multiple ecosystems, we need to declare where to fetch dependencies:
    
    *   Use Maven Central (and JCenter if needed) for Java, Kotlin, Scala, and Clojure artifacts.
        
    *   Add Clojars (the Clojure community repository) for Clojure libraries if needed (the Clojure plugin itself is on Gradle Portal, but Clojure libraries like `org.clojure:clojure` or others might be on Maven Central or Clojars). For example:
        
        ```kotlin
        repositories {
            mavenCentral()
            maven("https://repo.clojars.org/")  // Clojars for Clojure libs:contentReference[oaicite:2]{index=2}
            // ... (Gradle Plugin Portal is used internally for plugins)
        }
        ```
        
    *   Add RubyGems as a repository for JRuby gem dependencies. The JRuby Gradle plugin provides a way to resolve RubyGems. In Groovy DSL one could do `repositories { rubygems() }`. In Kotlin DSL, we must access the extension for RubyGems. For example:
        
        ```kotlin
        import com.github.jrubygradle.api.core.RepositoryHandlerExtension
        (repositories as org.gradle.api.plugins.ExtensionAware)
            .extensions.configure<RepositoryHandlerExtension>(repositories) {
                gems()  // enable RubyGems repository
            }
        ```
        
        This makes Ruby gems resolvable via Gradle[github.com](https://github.com/jruby-gradle/jruby-gradle-plugin/issues/407#:~:text=import%20com).
        
    *   The Jython plugin by Hierynomus automatically knows how to fetch packages from PyPI (Python Package Index) when we declare `jython` dependencies (it defines its own repository pattern for pip)[github.com](https://github.com/hierynomus/jython-gradle-plugin#:~:text=By%20default%20the%20following%20two,been%20defined%20for%20the%20plugin). We typically don’t need to add PyPI manually; the plugin does REST calls to PyPI to download packages[github.com](https://github.com/hierynomus/jython-gradle-plugin#:~:text=).
        
*   **Dependencies for each language:** Add the necessary runtime libraries and any language-specific dependencies:
    
    *   **Java/Scala/Kotlin:** These languages compile to class files directly. Ensure the Scala standard library is included (the Scala plugin does _not_ automatically add it). For example:
        
        ```kotlin
        dependencies {
            implementation("org.scala-lang:scala-library:2.13.11")  // Scala runtime library
            implementation(kotlin("stdlib"))  // Kotlin standard library
            // Java has no extra runtime dependency beyond the JDK
        }
        ```
        
        The Kotlin plugin will handle Kotlin reflection or stdlib if needed, but explicitly adding `kotlin("stdlib")` is a good practice. For Scala, choose a version compatible with your code. The Java and Kotlin plugins integrate naturally (Kotlin can call Java classes and vice versa), and Gradle will coordinate their compilation. Scala and Java also integrate (Gradle runs the Scala compiler which can also compile any Java sources for cross-language references). **Note:** Mixing Scala and Kotlin in the _same module_ can be tricky – if needed, consider separate subprojects for Scala and Kotlin sources[users.scala-lang.org](https://users.scala-lang.org/t/build-systems-for-scala/10227#:~:text=Build%20Systems%20for%20Scala%20,support%20soon%2C%20and%20sbt) to avoid compiler order issues.
        
    *   **Clojure:** Add the Clojure runtime as a dependency. Typically, include the same version of Clojure that you use to write the code. For example:
        
        ```kotlin
        dependencies {
            implementation("org.clojure:clojure:1.11.1")    // Clojure language runtime:contentReference[oaicite:7]{index=7}
        }
        ```
        
        The Clojurephant plugin will compile Clojure source files. By default it may only compile namespaces that are _explicitly_ AOT (ahead-of-time) compiled or needed for certain tasks. You can configure AOT compilation if you want `.class` files for your Clojure code (more on this later). In build.gradle.kts, one can do:
        
        ```kotlin
        clojure {
            builds {
                named("main") {
                    aotAll()  // compile all Clojure namespaces ahead-of-time
                }
            }
        }
        ```
        
        This ensures Clojure produces `.class` files for all namespaces in `src/main/clojure`, which is useful for generating Java-callable classes or speeding up startup[clojure.org](https://clojure.org/compilation#:~:text=Clojure%20compiles%20all%20code%20you,to%20use%20AOT%20compilation%20are).
        
    *   **JRuby (Ruby on JVM):** Include the JRuby engine and any Ruby gems needed:
        
        *   Add JRuby’s engine JAR. You have two options: **jruby-core** (engine without stdlib) or **jruby-complete** (engine + Ruby standard libraries). Using jruby-complete is simplest if you want a self-contained jar. For example,
            
            ```kotlin
            dependencies {
                implementation("org.jruby:jruby-complete:9.4.2.0")  // JRuby engine
            }
            ```
            
            (JRuby 9.4.x corresponds to Ruby 3.1 compatibility). The JRuby Gradle plugin might bring a default JRuby version, but explicitly including ensures the version.
            
        *   Declare Ruby gem dependencies via Gradle if needed. The JRuby plugin allows specifying gem coordinates as Gradle dependencies once RubyGems repo is enabled. For example, to include a Ruby gem `some_gem` version `1.0`:
            
            ```kotlin
            dependencies {
                implementation("rubygems:some_gem:1.0")
            }
            ```
            
            In older JRuby Gradle versions, a special configuration `gems` was used: e.g. `dependencies { gems "rubygems:asciidoctor-diagram:1.5.19" }`[stackoverflow.com](https://stackoverflow.com/questions/79205794/gradle-dsl-ruby-gems-build-fails#:~:text=dependencies%20%7B%20gems%20%27rubygems%3Aasciidoctor). In current JRuby/Gradle, using the `implementation` configuration with the `rubygems:` coordinate works similarly (the plugin sets up a Rubygems Maven proxy[github.com](https://github.com/jruby-gradle/jruby-gradle-plugin/issues/407#:~:text=The%20way%20this%20plugin%20configures,nice%20with%20the%20Kotlin%20DSL)).
            
        *   Place your Ruby source files under `src/main/ruby`. The JRuby Jar plugin (`com.github.jruby-gradle.jar`) will package these `.rb` files into the output JAR and ensure they can be executed via the JRuby runtime. You can also write JRuby code that will be pre-compiled or invoked at runtime (more on this under interoperability).
            
    *   **Jython (Python on JVM):** Include the Jython engine and Python libraries:
        
        *   Add Jython’s standalone JAR to run Python code on the JVM. For example:
            
            ```kotlin
            dependencies {
                implementation("org.python:jython-standalone:2.7.4")  // Jython 2.7.x
            }
            ```
            
            (Jython 2.7.4 is the latest stable supporting Python 2.7 syntax). This allows running Python code via Jython.
            
        *   Use the Jython Gradle plugin to fetch Python packages from PyPI if your project depends on any. The plugin introduces a custom dependency notation. For example:
            
            ```kotlin
            dependencies {
                jython(":boto3:1.1.3")
            }
            ```
            
            This will download the **boto3** Python library version 1.1.3 from PyPI and bundle it into the jar[github.com](https://github.com/hierynomus/jython-gradle-plugin#:~:text=The%20following%20example%20will%20download,it%20in%20your%20Jar%20file). The string format `":package:version"` (with an empty group) signals the plugin to use PyPI. You can also use the `python("name:artifact:version")` DSL for more control (e.g. specifying module names)[github.com](https://github.com/hierynomus/jython-gradle-plugin#:~:text=In%20some%20cases%2C%20the%20python,accordingly). The plugin will package these Python modules so they can be used at runtime.
            
        *   Place any of your own Python scripts in a directory (e.g. `src/main/python`). Jython can load `.py` files from the classpath, so bundling them in the jar as resources is sufficient. Ensure they are included (you might add `resources.srcDir("src/main/python")` in Gradle if needed, or treat them as part of the Jython plugin’s processing).
            

With these configurations, running Gradle will compile all languages. For example, `gradle compileKotlin compileJava compileScala compileClojure` will produce `.class` files from Kotlin, Java, Scala, and Clojure; JRuby and Jython don’t produce class files for scripts, but their files will be packaged. **Gradle’s Kotlin DSL** is fully supported, though certain plugin specifics (like adding the RubyGems repo) require using the extension APIs as shown above.

Common Language Interoperability Issues and Solutions
-----------------------------------------------------

Combining languages means components written in one language will need to interact with components in another. The JVM provides a common platform (Java bytecode), but differences in language paradigms can raise issues. Here are common challenges and how to address them:

*   **Type and API compatibility:** Each language has its own type system and standard library. When calling code across languages, be mindful of data types:
    
    *   **Java <-> Kotlin/Scala:** These are statically typed and have very good interop. Kotlin and Scala classes are compiled to Java-compatible classes. For example, Kotlin’s classes can be used in Java as normal (though Kotlin’s nullability is enforced only at compile-time in Kotlin). Scala’s classes (especially case classes or collections) can be used in Java, but some idioms (e.g. Scala’s `Option`) may need conversion to Java `Optional` manually. Conversely, Java classes are accessible in Kotlin and Scala without special effort. You may just need to add annotations or adapters if you want to idiomatically handle things like Java’s `Optional` in Scala or Kotlin.
        
    *   **Java/Kotlin/Scala <-> Clojure:** Clojure is dynamic and data-oriented. Calling Java-based code from Clojure is straightforward – Clojure has built-in Java interop syntax. For example, you call instance methods with `(.methodName object args...)` and static methods with `(ClassName/staticMethod args...)`. Clojure collections (lists, vectors, maps) implement Java interfaces (e.g. Clojure’s persistent vectors implement `java.util.List`), so you can pass them to Java methods expecting those interfaces. When **Java (or Kotlin/Scala) calls Clojure** code, it’s trickier: Clojure functions live in namespaces and by default are invoked through the Clojure runtime. One approach is **ahead-of-time (AOT) compiling** Clojure to generate Java classes. Clojure’s `gen-class` facility allows you to define a class in Clojure that implements interfaces or extends a Java class, exposing Clojure functions as true Java methods[clojure.org](https://clojure.org/compilation#:~:text=Clojure%20compiles%20all%20code%20you,to%20use%20AOT%20compilation%20are)[clojure.org](https://clojure.org/compilation#:~:text=,startup). For example, you could write a Clojure namespace with `(ns mylib.core (:gen-class ...))` and implement, say, a `public void invoke()` method. After AOT compile (which we enabled with `aotAll()` or could do per namespace), you’ll have a `.class` that Java can call directly. If you don’t want to AOT, an alternative is using Clojure’s runtime API: Java code can call `clojure.java.api.Clojure.var("myns", "my-fn").invoke(args...)` to invoke a function dynamically. This requires the Clojure runtime to be initialized (which happens if you included Clojure as a dependency). In summary, to make Java↔Clojure interop easier:
        
        *   Use AOT and `gen-class` for Clojure code that needs to be consumed by Java statically (this gives you named classes/interfaces as needed).
            
        *   Use Clojure’s Java interop for Clojure->Java calls (which is idiomatic and performant, especially if type hints are added to avoid reflection).
            
        *   Use the Clojure Java API or `IFn` interface for dynamic invocation if avoiding AOT. (Any Clojure function object implements `clojure.lang.IFn` with an `invoke` method overload.)
            
*   **Java/Kotlin/Scala <-> JRuby (Ruby):** JRuby runs Ruby code on the JVM. **Calling Java from Ruby** is supported out-of-the-box in JRuby. You can import Java classes or packages in Ruby using `include_package` or the `Java::` module. For example, in a JRuby script:
    
    ```ruby
    include Java
    import java.time.LocalDateTime
    puts LocalDateTime.now  # uses a Java class from Ruby
    ```
    
    JRuby will automatically map Java objects to Ruby proxies. Conversely, **calling Ruby from Java/Kotlin** requires an embedded JRuby runtime unless you have precompiled Ruby classes:
    
    *   _Dynamic invocation:_ Use the JSR 223 scripting API (Java’s standard way to run scripts). JRuby provides a `ScriptEngine` implementation. For example, in Java or Kotlin you can do:
        
        ```java
        ScriptEngineManager mgr = new ScriptEngineManager();
        ScriptEngine jrubyEngine = mgr.getEngineByName("jruby");
        jrubyEngine.eval("require 'mylibrary'"); 
        jrubyEngine.eval("MyRubyModule.do_something(123)");
        ```
        
        This evaluates Ruby code within a JRuby engine[nts.strzibny.name](https://nts.strzibny.name/using-ruby-gems-in-javagradle-projects-jruby/#:~:text=public%20class%20Main%20,jruby)[nts.strzibny.name](https://nts.strzibny.name/using-ruby-gems-in-javagradle-projects-jruby/#:~:text=rubyEngine.eval%28%20,amount%3A%20%27%24%20900%27%5Cn). Kotlin can use the same classes from `javax.script`. This approach is useful for calling into Ruby on the fly. It requires your Ruby code (and any gems) to be available on the classpath or loadable by JRuby (our Gradle setup ensures the Ruby files are packaged, and using `jrubyEngine.eval("require 'file.rb'")` can load them).
        
    *   _Compile Ruby to Java class:_ JRuby has an **ahead-of-time compiler** (the `jrubyc` tool) that can turn Ruby scripts into `.class` files. This is less commonly used, but it can generate Java bytecode for Ruby code. However, even compiled Ruby classes still depend on the JRuby runtime library. A more typical pattern is to write a Ruby class that **implements a Java interface or extends a Java class** so that it can be called from Java naturally. JRuby allows Ruby classes to implement Java interfaces simply by subclassing them. For example, if you have a Java interface `com.example.Task`, you can implement it in Ruby:
        
        ```ruby
        java_package 'com.example'
        class RubyTask < Java::com.example.Task
          def initialize; end
          def execute() 
            puts "Task executed"
          end
        end
        ```
        
        Now `RubyTask` is a Java class (under the package `com.example`) that implements `Task`. Java code could do `Task t = new RubyTask(); t.execute();` thanks to JRuby’s integration. Internally, JRuby creates a proxy class. This technique is powerful but requires the JRuby runtime present at runtime (which we have as a dependency). If creating such classes at runtime is inconvenient, you could AOT compile them.
        
        For simpler needs, using the scripting API or JRuby’s **JVM integration APIs** (`org.jruby.RubyInstanceConfig` and `org.jruby.embed.LocalVariableBehavior` etc.) lets you call Ruby code and retrieve results as Java types.
        
    *   **Data conversion:** JRuby will try to convert basic types between Ruby and Java (e.g. Ruby strings to `java.lang.String` when calling a Java method, or Java collections to Ruby `Array` when accessed in Ruby). You may sometimes need to manually convert types or use JRuby’s helper methods (`to_java` / `to_a` etc.) to get the desired types.
        
*   **Java/Kotlin/Scala <-> Jython (Python):** Jython is similar to JRuby in that Python code runs on the JVM. **Java from Python**: Jython allows using any Java class directly in Python code (just like in JRuby). In a Jython script, you can do:
    
    ```python
    from java.util import Date
    d = Date()  # create Java Date in Python
    print(d.getTime())
    ```
    
    Jython will handle conversion of primitive types seamlessly. **Calling Python from Java/Kotlin** is again a matter of embedding the interpreter or precompiling:
    
    *   Use JSR 223 scripting: Jython provides a `ScriptEngine` named “python”. You can load and execute Python code similarly:
        
        ```java
        ScriptEngine pyEngine = mgr.getEngineByName("python");
        pyEngine.eval("import mymodule"); 
        pyEngine.eval("result = mymodule.some_function(42)");
        Object result = pyEngine.get("result");
        ```
        
        This will run the Python code and you can fetch variables back. The result will be a Jython PyObject or a Java object depending on type.
        
    *   Another approach is using the Jython-specific API: `org.python.util.PythonInterpreter`. You can instantiate a `PythonInterpreter` in Java, execute scripts, and use `interp.get()` to retrieve variables.
        
    *   **Implementing interfaces in Python:** Like JRuby, Jython can implement Java interfaces in pure Python code[faculty.kutztown.edu](https://faculty.kutztown.edu/parson/pubs/JythonPACISE2011Talk.pdf#:~:text=Systems%20faculty,Jython%20can%20extend%20Java%20classes). If you define a Python class inheriting from a Java interface, Jython will create a compliant class. For example:
        
        ```python
        from java.lang import Runnable
        class PyTask(Runnable):
            def run(self):
                print("Task from Python")
        ```
        
        Now any Java method expecting a `java.lang.Runnable` can be passed an instance of `PyTask` (Jython will handle the proxying). One caution: Jython may not enforce interface method signatures at _compile_ time (because Python is dynamic), so you must ensure the methods are defined correctly to avoid runtime errors[stackoverflow.com](https://stackoverflow.com/questions/60637340/why-does-jython-not-enforce-the-interface-requirements-of-a-java-interface#:~:text=Why%20does%20Jython%20not%20enforce,when%20I%20made%20an)[faculty.kutztown.edu](https://faculty.kutztown.edu/parson/pubs/JythonPACISE2011Talk.pdf#:~:text=Systems%20faculty,Jython%20can%20extend%20Java%20classes).
        
    *   If you want to avoid the interpreter overhead each time, Jython had a tool called **jythonc** (in older versions) that could compile Python to Java classes. In modern Jython 2.7.x, jythonc is deprecated, so the recommended approach is either dynamic invocation or writing Java-callable wrappers (like the interface implementation above).
        
    *   **Data conversion:** Jython’s objects (e.g. `PyString`, `PyList`) often subclass or are convertible to Java equivalents. For instance, Jython’s `PyList` implements `java.util.List` so you can pass it to Java directly[faculty.kutztown.edu](https://faculty.kutztown.edu/parson/pubs/JythonPACISE2011Talk.pdf#:~:text=Systems%20faculty,Jython%20can%20extend%20Java%20classes). Primitive types and strings usually auto-convert. If a Java API returns a collection, Jython may present it as a Python list via integration.
        
*   **Clojure <-> JRuby/Jython (Dynamic <-> Dynamic):** Direct interaction between, say, Ruby and Clojure code on the JVM is less common, but possible since all share the JVM. Typically, they would communicate via Java interfaces or classes as an intermediary. For example, you might have a Java interface that both a Clojure class (via gen-class) and a JRuby class implement; then they can be used interchangeably by Java code. Without an interface, one dynamic language can still call the other by going through Java: e.g., JRuby can call Clojure by using the Clojure Java API to invoke a function, or Clojure can call JRuby by using the JRuby embed API. These are advanced scenarios – a simpler approach is to refactor shared logic into Java/Kotlin (which both Ruby and Clojure can call easily) if you find yourself needing a lot of cross-calling between dynamic languages.
    
*   **Threading and state:** All these languages run on the JVM, so threads and memory are shared. If you have mutable state, be mindful of thread safety across languages. For example, a Java thread might call a Clojure function – that function might internally use Clojure’s STM or other concurrency primitives which are thread-safe, but if sharing data, ensure any concurrency primitives are respected across languages. In general, Java’s synchronization locks are usable by any JVM language (a Ruby `synchronized {}` block or a Python `with threading.Lock():` will ultimately use JVM locks). Garbage collection is unified on the JVM, so you don’t need to manage separate GCs, but finalization or resource management might differ (Clojure relies on Java GC, JRuby/Jython also rely on JVM GC for memory but have their own heap for objects). Usually these differences do not require special action, just be aware that (for example) JRuby’s objects are garbage-collected by the JVM like any Java object.
    
*   **Exception handling:** Exceptions can be tricky cross-language. A Java exception thrown will bubble through Clojure or JRuby code as a Java exception (JRuby will wrap it in a Ruby `RuntimeError` if not caught in Ruby, but if not caught at all it can be seen as a Java exception too). Similarly, if a JRuby script throws a Ruby exception and it isn’t caught, when it propagates to Java it will typically be an instance of `org.jruby.exceptions.RaiseException` (with the Ruby traceback inside). You may need to catch the language-specific exception classes in Java, or catch a general `Exception` and inspect cause. The key is to decide which side to handle errors on – often it’s easiest to catch and translate exceptions at the boundary (e.g., catch a Python exception in Jython and throw a Java exception with the message for the Java code).
    

**Making interactions easier or more idiomatic:**

*   Define clear **interfaces or abstract classes** in Java that serve as contracts between languages. This way, dynamic languages can implement those interfaces (as shown for JRuby/Jython), and static languages can call them without worrying about the implementation details. This is a common pattern to keep things modular.
    
*   Use each language for what it’s best at, and call across when needed, but avoid overly chatty cross-language calls. Each cross-language call may incur conversion overhead (e.g., converting a large data structure from a Clojure persistent map to a Java `HashMap` or to a JRuby hash could be expensive). If heavy data manipulation is needed, consider doing it on one side and only passing final results across.
    
*   When designing API, consider providing thin idiomatic wrappers in each language:
    
    *   For example, your core logic might be in Java, but you could write a small Clojure namespace with functions that call the Java static methods in a way that feels natural to Clojure users (accepting Clojure data structures, converting to Java, calling the Java code, then converting results back to Clojure types).
        
    *   For JRuby, you might provide a Ruby module that wraps around the Java classes or calls, so Ruby users can call a Ruby-style method which under the hood invokes the Java logic. (JRuby makes it easy to call Java, but a wrapper can hide Javaisms and provide a more Ruby-like API).
        
    *   For Jython/Python, similarly, a pure Python module can wrap Java calls (e.g., providing a Python function instead of requiring the user to interact with Java classes directly).
        
*   **Documentation and examples** are important: show how to use the final library from each language. For instance, demonstrate how a Scala developer would use it (probably just adding the JAR and calling the classes), how a Clojure developer would use it (perhaps by requiring the Clojure namespace or interop with Java classes), how a JRuby user would require the gem, etc. Making usage frictionless in each language’s ecosystem is key to an idiomatic experience.
    

Packaging the Polyglot Library
------------------------------

After building the project, packaging and distributing it in a convenient form is crucial. We have two broad approaches:

1.  **Single fat JAR distribution**, containing all code and dependencies (except perhaps language runtimes if not desired).
    
2.  **Modular, Maven-published artifacts** for each facet, and optionally language-specific packaging (Ruby gems, Python wheels) for dynamic language ecosystems.
    

### 1\. Fat JAR (Uber JAR) Approach

A **fat JAR** bundles everything into one JAR file – your code from all languages plus all required dependency libraries. The result can be a standalone library or even an executable (if you include a main class). In our case, a fat JAR could include the Scala library, Clojure runtime, JRuby engine, Jython engine, and any gems or Python packages used – essentially one file that works anywhere on a JVM.

**How to create a fat JAR in Gradle:** One popular plugin is the Gradle Shadow plugin. You can apply `id("com.github.johnrengelman.shadow") version "7.1.2"` (for example) and then run `gradle shadowJar`. This will produce a `*-all.jar` that contains all project classes and dependencies. If using the Shadow plugin, you might mark some dependencies as provided if you don’t want them included (for example, if you expect JRuby to be provided by the runtime environment, you could exclude it).

However, since we applied the **JRuby Jar plugin**, it already can create an _uberjar_ for JRuby projects. The JRuby Gradle plugin’s `jar` portion will include Ruby code and can also embed the JRuby runtime. In fact, the JRuby Gradle plugin exists to _“build jar files… and much more”_ combining Ruby and Java[github.com](https://github.com/jruby-gradle/jruby-gradle-plugin#:~:text=JRuby%2FGradle%20brings%20the%20power%20and,run%20tests%2C%20and%20much%20more). We would configure it to include the JRuby engine (`jruby-complete`) so that the JAR can run Ruby code standalone. Similarly, the Jython plugin by Hierynomus, when we added `jython` dependencies, ensures those Python libraries (and likely the Jython runtime if on classpath) are bundled in the output JAR[github.com](https://github.com/hierynomus/jython-gradle-plugin#:~:text=The%20following%20example%20will%20download,it%20in%20your%20Jar%20file). So simply running Gradle’s standard `jar` task in this setup may already produce a jar containing:

*   All `.class` files from Java, Kotlin, Scala, Clojure.
    
*   All Ruby `.rb` files (the JRuby plugin will package them, possibly under a path and include a `jruby-core` jar inside if configured).
    
*   All Python `.py` files or extracted packages (the Jython plugin by default unpacks the Python packages into the jar).
    
*   The runtime libraries: JRuby and Jython engines, Clojure, Scala library, etc, if they are listed as implementation dependencies.
    

You will need to ensure that your jar’s **Manifest** has the correct Main-Class if this jar is meant to be executable. The JRuby plugin can create a _self-contained JRuby jar_ with an entry point (e.g., to run a specific Ruby script). If your library is not an application, you might not need a main class.

**Pros of fat JAR:** One file to distribute; easy for Java/Scala developers to drop in and use. It ensures consistent versions of everything. Also, it’s convenient for testing – you know all pieces are present.

**Cons:** Fat JARs can be large (because they include e.g. the entire JRuby stdlib and Jython, which together could be tens of MB). If a user only needs some parts (say they only use the Java API and don’t care about Ruby/Python), they still have the overhead. Also, if distributing to environments that already have those languages, a fat JAR duplicates them (for instance, a JRuby user running on JRuby already has the JRuby runtime – bundling it again in the jar is redundant).

**Shading and conflicts:** If you do a fat jar, you should be mindful of duplicate classes (for example, JRuby and Jython both include some common libraries like ASM for bytecode manipulation or logging libraries – Shadow plugin can relocate packages if necessary to avoid conflicts). Ensure that your fat jar doesn’t have conflicting versions of the same class. In practice, using consistent dependency versions and shading where needed solves this.

### 2\. Modular Maven Artifacts (and Language-specific Packages)

In this approach, we produce a set of artifacts that can be published to appropriate repositories:

*   **JVM artifacts (JARs)**: You might publish a core JAR (with just your compiled classes and maybe resource files from dynamic languages) to Maven Central. This JAR would declare dependencies on needed runtimes rather than include them. For example, your `mylib.jar` can have `org.jruby:jruby-complete` and `org.python:jython-standalone` as Maven dependencies (so users can pull them if needed). You could also split artifacts by language:
    
    *   `mylib-core.jar`: containing the core Java/Scala/Kotlin/Clojure compiled classes.
        
    *   `mylib-ruby.jar`: containing Ruby code and possibly JRuby-specific helper classes (but not the JRuby engine).
        
    *   `mylib-python.jar`: containing Python scripts or wrappers (but not the Jython engine).  
        In many cases, a single jar with everything _except_ the heavy runtime engines is sufficient; JRuby and Jython can be regular dependencies. This keeps the artifact size smaller while still making it easy for any JVM user to include the library. A Java/Scala/Clojure developer would include `mylib` and also get JRuby/Jython on the classpath (if your pom lists them). If they don’t need JRuby/Jython, they could exclude those transitive deps.
        
*   **Ruby Gem (for JRuby users):** To cater to JRuby users in their native workflow, you can package a Ruby gem. There are two strategies:
    
    1.  **Pure-Java gem**: Some JRuby gems include Java bytecode. You can take the core JAR you built and add it into a gem. For example, create a gem structure with:
        
        *   `lib/mylib.jar` (your jar file)
            
        *   `lib/mylib.rb` (a bootstrap Ruby file)
            
        *   `mylib.gemspec`
            
        
        In the gemspec, you can declare a dependency on the `jar-dependencies` gem and list the Maven coordinates of your jar or other jars. The **jar-dependencies** library allows a gem to automatically pull down JAR files from Maven Central when the gem is installed or required[stackoverflow.com](https://stackoverflow.com/questions/35461309/jruby-gemspec-local-jar-dependencies#:~:text=,adapter)[stackoverflow.com](https://stackoverflow.com/questions/35461309/jruby-gemspec-local-jar-dependencies#:~:text=s.requirements%20%3C%3C%20,dependencies). For instance, in the gemspec:
        
        ```ruby
        s.name = "mylib"
        s.version = "1.0"
        s.summary = "My polyglot library"
        s.require_paths = ["lib"]
        s.files = Dir["lib/**/*"] + ["mylib.gemspec"]
        # Declare jar dependencies:
        s.add_runtime_dependency "jar-dependencies", "~> 0.4"
        s.requirements << "jar 'com.mycompany:mylib:1.0'" 
        ```
        
        The above line tells jar-dependencies to fetch the Maven artifact `com.mycompany:mylib:1.0` (which would be the JAR you published to Maven). This way, the gem doesn’t even need to include the jar – it can download the correct version from Maven at runtime[stackoverflow.com](https://stackoverflow.com/questions/35461309/jruby-gemspec-local-jar-dependencies#:~:text=,adapter)[stackoverflow.com](https://stackoverflow.com/questions/35461309/jruby-gemspec-local-jar-dependencies#:~:text=s.requirements%20%3C%3C%20,dependencies). The user experience for JRubyists is: they install the gem, and when they `require 'mylib'`, jar-dependencies will ensure the JAR is on the classpath.
        
        Alternatively, you could **vendor** the jar inside the gem (include `lib/mylib.jar` in the gem files) and then in `lib/mylib.rb`, write:
        
        ```ruby
        require 'java'
        require_relative 'mylib.jar'
        # perhaps load some Ruby integration code or simply let users use the Java API
        ```
        
        This approach doesn’t require downloading from Maven (the jar travels with the gem), but it makes the gem larger. It’s simpler for offline use. You can still use jar-dependencies but point it to a local jar path.
        
        If your library also has Ruby source code (e.g., idiomatic Ruby wrapper methods), include those `.rb` files in the gem’s `lib/` as usual. JRuby will be able to use both the Ruby code and the classes inside the jar.
        
    2.  **JRuby Gradle plugin gem tasks:** The JRuby Gradle plugin primarily focuses on jars and wars, not gem building. There isn’t a built-in “gem assemble” task in the plugin (its goal is more to let Ruby devs use Gradle for jar/war packaging). So building a gem might involve writing a small Rake task or using RubyGems tooling. You could automate gem building in Gradle by invoking JRuby and running `gem build`. For example, using the Gradle JRuby plugin’s exec capabilities:
        
        ```kotlin
        tasks.register("buildGem", Exec::class) {
            dependsOn(jar)  // ensure jar is built
            commandLine("jruby", "-S", "gem", "build", "mylib.gemspec")
        }
        ```
        
        (This assumes JRuby is installed or you use the plugin’s JRubyExec which knows the JRuby in classpath.) This will produce `mylib-1.0.gem` which you can publish to RubyGems.org for JRuby users.
        
    
    Once published, JRuby users can `gem install mylib` and then `require 'mylib'`. Thanks to the packaging, this will load your library. They can then call any Java classes from it, or use any Ruby-friendly API you provided. The gem’s platform can be marked `java` in the gemspec (to indicate it’s only for JRuby). For example: `s.platform = 'java'`.
    
*   **Python Package (for Jython users):** Jython users typically use Python’s packaging. You can create a Python wheel or egg for your library:
    
    *   Write a `setup.py` for your project that includes your Python modules and any Java JARs as package data. For example, include the core JAR in the `package_data` so that it ends up inside the wheel. You might also decide not to include the Jython runtime itself (Jython users will have Jython), but include your library’s jar.
        
    *   In your Python module (e.g., `mylib/__init__.py`), ensure the JAR is added to the classpath. One convenient trick: Jython will scan the `sys.path` for `.jar` files and load them as Java libraries[jython.readthedocs.io](https://jython.readthedocs.io/en/latest/ModulesPackages/#:~:text=Chapter%208%3A%20Modules%20and%20Packages,This%20has%20the). If your jar is installed in the site-packages, you can append its path to `sys.path` at runtime. For instance:
        
        ```python
        import pkg_resources, sys
        jar_path = pkg_resources.resource_filename(__name__, "mylib.jar")
        if jar_path not in sys.path:
            sys.path.append(jar_path)
        ```
        
        This will add the jar from your package to Jython’s classpath dynamically. After that, you can `import com.mycompany.MyClass` or whatever classes directly in Jython.
        
    *   Alternatively, instruct users to put the JAR on Jython’s classpath (less ideal for a Python-first user). The wheel approach makes it seamless – a Jython user can `pip install mylib`, then in their Jython environment do `import mylib` and your initialization code loads the jar.
        
    *   You might also provide a pure-Python API wrapping the Java calls. For example, if your library has a class `com.mycompany.Foo` with method `doThing(int)`, you can in `mylib/__init__.py` write a Python function:
        
        ```python
        from com.mycompany import Foo
        def do_thing(x):
            return Foo.doThing(x)
        ```
        
        So a Jython user calls `mylib.do_thing(5)` and under the hood it calls the Java logic.
        
    *   **Publishing to PyPI:** Use standard Python tooling (setuptools/twine) to upload the wheel. Note that Jython 2.7 corresponds to Python 2 syntax; if you also want to support usage on CPython (maybe your library’s Python API could work on CPython via JPype or similar bridging, but that’s another story), you’d need to maintain Python 3 compatibility separately. Likely, this library is mainly for Jython, so Python 2 syntax is fine.
        
*   **Standard JAR publication:** Use Gradle’s `maven-publish` plugin to publish your JARs to Maven Central (or a company Nexus/Artifactory). You’d create a publication for the main jar and any auxiliary jars (if you split core and -ruby, -python jars). Many organizations keep it simple with one jar. The artifacts should include POM entries for dependencies:
    
    *   E.g. your POM can list `org.jruby:jruby-complete` as a dependency, so if a Java developer uses Maven to add your library, they automatically get JRuby on their classpath (needed if they want the Ruby part to work). If they don’t need it, they can exclude it. This approach offloads the decision to the user.
        
    *   If you published separate modules, you might have `mylib-core` (with no JRuby dependency) and a `mylib-jruby` (that depends on core and on JRuby and includes the Ruby files). A JRuby user could just use the gem in that case, but a Java developer who wants to use the Ruby portion might explicitly add `mylib-jruby`. This modular approach is nice for optional components.
        

**Summary of packaging choices:** For maximum reach:

*   Publish the core JAR to Maven (so Java, Scala, Clojure, Kotlin developers can get it easily).
    
*   Publish a Ruby gem for JRuby users (possibly including or auto-fetching the core JAR).
    
*   Publish a Python wheel for Jython users (including the core JAR).
    

This covers all ecosystems. In practice, JRuby usage in the wild might simply use the Maven coordinates via jar-dependencies (so the gem approach is one way or they could directly use the JAR if they know how). Jython is less common these days (limited to Python 2.7), but enterprise users might appreciate a ready-to-go package.

Tool and Plugin Recommendations
-------------------------------

To implement the above effectively, here’s a quick list of useful tools and documentation:

*   **Gradle plugins:**
    
    *   _Kotlin JVM Plugin:_ Official Kotlin plugin (see Kotlin docs on Gradle setup[kotlinlang.org](https://kotlinlang.org/docs/gradle-configure-project.html#:~:text=Configure%20a%20Gradle%20project%20,and%20configure%20the%20project%27s)).
        
    *   _Scala Plugin:_ Built-in Gradle plugin (Gradle documentation has a sample for Scala and Java in one project[discuss.gradle.org](https://discuss.gradle.org/t/multiple-language-plugins-for-one-project-is-it-supported-e-g-java-scala/3569#:~:text=Multiple%20language%20plugins%20for%20one,any%20issues%20on%20Gradle%27s%20side)).
        
    *   _Clojurephant Plugin:_ Gradle plugin for Clojure. Documentation and guides are available on clojurephant.dev (the Quick Start we cited shows how to add Clojure and Clojars repo[github.com](https://github.com/clojurephant/clojurephant#:~:text=repositories%20,)).
        
    *   _JRuby-Gradle Plugin:_ Plugin by the JRuby community. See the jruby-gradle GitHub for usage. It allows declaring `rubygems:` dependencies and packaging JRuby jars. _(Note:_ When using Kotlin DSL, you may need the ExtensionAware trick to call `gems()` on repositories due to a known issue[github.com](https://github.com/jruby-gradle/jruby-gradle-plugin/issues/407#:~:text=The%20way%20this%20plugin%20configures,nice%20with%20the%20Kotlin%20DSL).)
        
    *   _Jython Gradle Plugin:_ Available on Gradle Plugin Portal as `com.github.hierynomus.jython`. The README on GitHub shows examples of dependency notation and configuration[github.com](https://github.com/hierynomus/jython-gradle-plugin#:~:text=The%20following%20example%20will%20download,it%20in%20your%20Jar%20file).
        
    *   _Shadow Plugin:_ For fat jar creation, if not relying on jruby-gradle’s jar task.
        
    *   _Maven Publish Plugin:_ To publish jars to Maven Central.
        
*   **Language documentation:**
    
    *   _Clojure AOT and gen-class:_ Official Clojure documentation on compilation[clojure.org](https://clojure.org/compilation#:~:text=Clojure%20compiles%20all%20code%20you,to%20use%20AOT%20compilation%20are) and the `gen-class` function (useful for interop).
        
    *   _JRuby documentation:_ The JRuby Wiki has info on embedding JRuby and calling Java from Ruby. The JRuby org blog posts can be helpful for examples.
        
    *   _Jython documentation:_ The older “Definitive Guide to Jython” (especially chapters on Jython and Java integration) covers implementing interfaces and using Jython in Java applications[faculty.kutztown.edu](https://faculty.kutztown.edu/parson/pubs/JythonPACISE2011Talk.pdf#:~:text=Systems%20faculty,Jython%20can%20extend%20Java%20classes).
        
    *   _Jar-dependencies gem:_ The README in the jar-dependencies project explains how gems can declare Maven jars[stackoverflow.com](https://stackoverflow.com/questions/35461309/jruby-gemspec-local-jar-dependencies#:~:text=,adapter). If you plan to use that in your gemspec, it’s good to read their guidelines (e.g., all jars must come from Maven Central by default[github.com](https://github.com/jruby/jar-dependencies#:~:text=JARs%20other%20than%20from%20maven)).
        
*   **Community examples:** Look at projects that have done multi-language packaging. For instance, the AsciidoctorJ project uses JRuby under the hood but provides a Java API – their build might offer insight (they use AsciidoctorJ as a jar and also have a gem for Asciidoctor Ruby). Another example: see how Apache Beam or other cross-language systems package things (though those often use separate adapters).
    

Conclusion
----------

Building a polyglot library on the JVM is certainly challenging, but Gradle’s support for multiple languages makes it feasible to organize one project with all source code. By applying the right plugins and following language-specific conventions, you can compile everything together[discuss.gradle.org](https://discuss.gradle.org/t/multiple-language-plugins-for-one-project-is-it-supported-e-g-java-scala/3569#:~:text=Multiple%20language%20plugins%20for%20one,any%20issues%20on%20Gradle%27s%20side). Interoperability requires designing clear boundaries – often using Java interfaces or making use of each language’s ability to call into Java – but as we saw, each pairing has known solutions (from Clojure’s AOT for Java usage[clojure.org](https://clojure.org/compilation#:~:text=Clojure%20compiles%20all%20code%20you,to%20use%20AOT%20compilation%20are), to dynamic languages implementing interfaces for callback patterns[faculty.kutztown.edu](https://faculty.kutztown.edu/parson/pubs/JythonPACISE2011Talk.pdf#:~:text=Systems%20faculty,Jython%20can%20extend%20Java%20classes), to using the JSR223 scripting API for on-the-fly calls). Finally, packaging is about meeting developers where they are: a Java developer will prefer a Maven dependency (or one fat jar), a Ruby developer will appreciate a gem that just works, and a Python developer using Jython will expect a pip-installable package. By producing both a fat JAR **and** ecosystem-specific packages, you maximize usability.

With this approach, you can write components of your library in the language that suits each task best (e.g. use Clojure for flexible data transformation, use Kotlin/Java for performance-critical parts, maybe use Ruby/Python for simple scripting or DSLs), and deliver a cohesive library. Gradle handles the heavy lifting of compilation and assembly, allowing you to focus on making the languages play nicely together.

**Sources:**

1.  Gradle Forum – Confirming multi-language plugin support[discuss.gradle.org](https://discuss.gradle.org/t/multiple-language-plugins-for-one-project-is-it-supported-e-g-java-scala/3569#:~:text=Multiple%20language%20plugins%20for%20one,any%20issues%20on%20Gradle%27s%20side)
    
2.  Clojurephant (Gradle Clojure) usage example – adding Clojure and Clojars[github.com](https://github.com/clojurephant/clojurephant#:~:text=repositories%20,)
    
3.  Stack Overflow – Gradle gem dependency example using JRuby plugin[stackoverflow.com](https://stackoverflow.com/questions/79205794/gradle-dsl-ruby-gems-build-fails#:~:text=dependencies%20%7B%20gems%20%27rubygems%3Aasciidoctor)
    
4.  Hierynomus Jython Gradle Plugin – Example of bundling a PyPI package[github.com](https://github.com/hierynomus/jython-gradle-plugin#:~:text=The%20following%20example%20will%20download,it%20in%20your%20Jar%20file)
    
5.  Clojure.org – Importance of AOT for generating Java-usable classes[clojure.org](https://clojure.org/compilation#:~:text=Clojure%20compiles%20all%20code%20you,to%20use%20AOT%20compilation%20are)
    
6.  Jython integration PDF – Jython can extend Java classes/interfaces[faculty.kutztown.edu](https://faculty.kutztown.edu/parson/pubs/JythonPACISE2011Talk.pdf#:~:text=Systems%20faculty,Jython%20can%20extend%20Java%20classes)
    
7.  Stack Overflow – JRuby gemspec declaring Maven jar dependencies[stackoverflow.com](https://stackoverflow.com/questions/35461309/jruby-gemspec-local-jar-dependencies#:~:text=,adapter)