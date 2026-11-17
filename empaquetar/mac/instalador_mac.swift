// =============================================================================================================================
// Contents/MacOS/instalar de «Instalar Comprobantes.app» (la app del .dmg): la ventana del instalador, NATIVA (AppKit + SwiftUI).
// Mismo método que el de CineCaptions (v5.92, a su vez de CineSlide): un doble clic → instala → se cierra → abre Comprobantes y
// queda en el Dock. Simple, sin contraseña.
// - Si Comprobantes Cinema ya está instalado con esta versión o una más nueva, solo lo abre.
// - Si no: ventana mínima (560 × 400): el logo dentro de un anillo que ES el progreso, qué está haciendo (los MB mientras copia),
//   el porcentaje grande y un punto por paso: 1) Comprobantes en Aplicaciones (o en ~/Aplicaciones si no hay permiso),
//   2) la app en el Dock. Al terminar abre Comprobantes en el acto, se cierra y expulsa el disco. Si falla: el motivo y «Cerrar».
// - El programa viaja OCULTO en el disco, junto a esta app («.Comprobantes Cinema.app») y no dentro: así esta app pesa poco y
//   macOS no revisa cientos de MB antes de mostrar la ventana (aparece al instante). Si macOS la abre «trasladada»
//   (App Translocation: una copia aparte, sin lo que tiene al lado), se busca en el disco montado (/Volumes/Comprobantes…).
// - ⌘Q se puede siempre: copia a «….app.nuevo» y recién al final cambia el nombre (nunca queda nada a medias).
//   instalar --demo | --demo-error      simula una instalación (para ver el diseño y sacar capturas)
// Lo compila empaquetar/crear_instalador_mac.sh en una Mac (swiftc, solo arm64: Apple Silicon); Windows no puede.
// =============================================================================================================================
import AppKit
import SwiftUI

// ---------------------------------------------------------------------------------------------------------------- colores
extension Color {
    init(hex: UInt32, a: Double = 1) {
        self.init(.sRGB, red: Double((hex >> 16) & 0xff) / 255, green: Double((hex >> 8) & 0xff) / 255,
                  blue: Double(hex & 0xff) / 255, opacity: a)
    }
}

let ROJO = Color(hex: 0xe5252a), CORAL = Color(hex: 0xff4d52), DORADO = Color(hex: 0xffb35c)
let TEXTO = Color(hex: 0xf4f1f2), SUAVE = Color(hex: 0xb3abae), TENUE = Color(hex: 0x6e676a)
let VERDE = Color(hex: 0x22c55e), MENTA = Color(hex: 0x7af0b0), AMBAR = Color(hex: 0xf5b84b), ERROR = Color(hex: 0xff6b6b)

let NOMBRE = "Comprobantes Cinema"
let APP = NOMBRE + ".app"
let OCULTA = "." + APP
let BINARIO = "Contents/MacOS/" + NOMBRE
let PASOS = ["Comprobantes en Aplicaciones", "App en el Dock"]
let NPASOS = 2
// porcentaje al empezar y al terminar cada paso (0 = preparar) y segundos típicos: dentro de un paso la barra avanza sola hacia
// su final sin llegar, así nunca se ve detenida; mientras copia, sigue los MB copiados
let TRAMOS: [(Double, Double)] = [(0, 3), (3, 90), (90, 98)]
let DURACION: [Double] = [0.5, 7, 0.8]

let HOME = NSHomeDirectory()

func numeroVersion(_ v: String) -> Int {
    let p = v.split(separator: ".").map { Int($0) ?? 0 }
    return (p.count > 0 ? p[0] : 0) * 1_000_000 + (p.count > 1 ? p[1] : 0) * 1_000 + (p.count > 2 ? p[2] : 0)
}

func versionDe(_ app: String) -> String? {
    guard let d = NSDictionary(contentsOfFile: app + "/Contents/Info.plist") else { return nil }   // (sin caché)
    return d["CFBundleShortVersionString"] as? String
}

func esApp(_ ruta: String) -> Bool { FileManager.default.isExecutableFile(atPath: ruta + "/" + BINARIO) }

// la instalada MÁS NUEVA (puede haber dos: la de /Applications y la de este usuario en ~/Applications)
func appInstalada() -> String? {
    var mejor: (ruta: String, v: Int)? = nil
    for ruta in ["/Applications/" + APP, HOME + "/Applications/" + APP] where esApp(ruta) {
        let v = numeroVersion(versionDe(ruta) ?? "0")
        if mejor == nil || v > mejor!.v { mejor = (ruta, v) }
    }
    return mejor?.ruta
}

@discardableResult
func ejecutar(_ programa: String, _ argumentos: [String]) -> (Int32, String) {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: programa)
    p.arguments = argumentos
    let tubo = Pipe()
    p.standardOutput = tubo
    p.standardError = tubo
    p.standardInput = FileHandle.nullDevice
    do { try p.run() } catch { return (-1, error.localizedDescription) }
    let datos = tubo.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    return (p.terminationStatus, String(decoding: datos, as: UTF8.self))
}

func megas(_ ruta: String) -> Double {
    let (st, salida) = ejecutar("/usr/bin/du", ["-sk", ruta])
    guard st == 0, let kb = Double(salida.split(whereSeparator: { $0 == "\t" || $0 == " " }).first ?? "") else { return 0 }
    return kb / 1024
}

func abrir(_ app: String) {
    NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: app), configuration: NSWorkspace.OpenConfiguration()) { _, _ in }
}

// el programa que trae el disco: oculto junto a esta app; para pruebas, dentro de ella; si macOS la trasladó, en el disco montado
func buscarPaquete(_ version: String) -> String? {
    let alLado = (Bundle.main.bundlePath as NSString).deletingLastPathComponent + "/" + OCULTA
    if esApp(alLado) { return alLado }
    let dentro = (Bundle.main.resourcePath ?? "") + "/" + APP
    if esApp(dentro) { return dentro }
    var otra: String? = nil
    // (solo los discos «Comprobantes …»: mirar dentro de otros —externos, de red— podía pedir permiso o colgarse)
    for v in (try? FileManager.default.contentsOfDirectory(atPath: "/Volumes")) ?? [] where v.hasPrefix("Comprobantes") {
        let r = "/Volumes/" + v + "/" + OCULTA
        guard esApp(r) else { continue }
        if versionDe(r) == version { return r }
        if otra == nil { otra = r }
    }
    return otra
}

// ---------------------------------------------------------------------------------------------------------------- avance
final class Avance: ObservableObject {
    @Published var paso = 0
    @Published var aviso = ""
    @Published var estado = "instalando"           // instalando | listo | error
    @Published var mensaje = ""
    @Published var valor: Double = 0
    @Published var mbHecho: Double = 0
    @Published var mbTotal: Double = 0
    var tPaso = Date()

    func evento(_ tipo: String, _ texto: String = "") {
        guard estado == "instalando" else { return }
        switch tipo {
        case "PASO":
            if let n = Int(texto), n > paso { paso = n; tPaso = Date(); aviso = "" }
        case "AVISO":
            aviso = texto
        case "FALLO":
            estado = "error"; mensaje = texto.isEmpty ? "Algo salió mal." : texto
        case "FIN":
            estado = "listo"
        default:
            break
        }
    }

    func objetivo() -> Double {
        if estado == "listo" { return 100 }
        let i = min(max(paso, 0), NPASOS)
        let (a, b) = TRAMOS[i]
        if i == 1 && mbTotal > 0 {                              // copiando: sigue los MB de verdad
            return a + (b - a) * min(0.99, mbHecho / mbTotal)
        }
        let k = Date().timeIntervalSince(tPaso)
        return a + (b - a) * min(1, 0.9 * (1 - exp(-k / DURACION[i])))
    }

    func avanzar(_ dt: Double) {
        let obj = objetivo()
        valor += (obj - valor) * min(1, dt * (estado == "listo" ? 6 : 3))
    }
}

// ---------------------------------------------------------------------------------------------------------------- vista
struct BotonPildora: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 14, weight: .bold))
            .foregroundColor(.white)
            .padding(.horizontal, 30).frame(height: 40)
            .background(Capsule().fill(LinearGradient(colors: [ROJO, CORAL], startPoint: .leading, endPoint: .trailing)))
            .opacity(configuration.isPressed ? 0.8 : 1)
    }
}

let ANCHO: CGFloat = 400, ALTO: CGFloat = 350   // minimalista: anillo, una palabra y el porcentaje

struct VistaInstalador: View {
    @ObservedObject var av: Avance
    let version: String
    let icono: NSImage?
    let cerrar: () -> Void

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 60.0)) { ctx in
            let t = ctx.date.timeIntervalSinceReferenceDate
            ZStack(alignment: .top) {
                LinearGradient(colors: [Color(hex: 0x1d1316), Color(hex: 0x0c0b0d)], startPoint: .topLeading,
                               endPoint: UnitPoint(x: 0.75, y: 1))
                Ellipse()
                    .fill(RadialGradient(colors: [colorEstado.opacity(0.18 + 0.05 * sin(t * 1.6)), colorEstado.opacity(0)],
                                         center: .center, startRadius: 0, endRadius: 220))
                    .frame(width: ANCHO, height: ALTO).offset(y: -100)
                VStack(spacing: 0) {   // centrado en la ventana; «Cerrar» (solo si falla) abajo
                    Spacer(minLength: 24)
                    anillo(t).frame(width: 150, height: 150)
                    titulo.padding(.top, 20)
                    detalle.padding(.top, 8).padding(.horizontal, 32)
                    cifra.padding(.top, 2)
                    Spacer(minLength: 14)
                    pie.padding(.bottom, 22)
                }
                .frame(width: ANCHO, height: ALTO)
            }
            .frame(width: ANCHO, height: ALTO)
            .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).stroke(colorBorde, lineWidth: 1.2))
        }
    }

    var colorEstado: Color { av.estado == "error" ? ERROR : (av.estado == "listo" ? VERDE : ROJO) }
    var colorBorde: Color {
        av.estado == "listo" ? VERDE.opacity(0.6) : (av.estado == "error" ? ERROR.opacity(0.6) : Color(hex: 0x3a2a2e))
    }

    // ---- el logo dentro del anillo de progreso
    func anillo(_ t: Double) -> some View {
        let frac = av.estado == "listo" ? 1 : max(0.02, min(1, av.valor / 100))
        let colores: [Color] = av.estado == "error" ? [Color(hex: 0xc2444a), ERROR]
            : (av.estado == "listo" ? [VERDE, MENTA, VERDE] : [ROJO, CORAL, DORADO])
        let ang = (frac * 360 - 90) * .pi / 180
        return ZStack {
            Circle().stroke(Color.white.opacity(0.08), lineWidth: 5).frame(width: 145, height: 145)
            Circle().trim(from: 0, to: frac)
                .stroke(AngularGradient(gradient: Gradient(colors: colores), center: .center,
                                        startAngle: .degrees(0), endAngle: .degrees(360 * frac)),
                        style: StrokeStyle(lineWidth: 5, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .frame(width: 145, height: 145)
            if av.estado == "instalando" {                       // la punta, con brillo que late
                Circle().fill(CORAL).frame(width: 12, height: 12)
                    .shadow(color: CORAL.opacity(0.55 + 0.3 * sin(t * 4)), radius: 7)
                    .offset(x: cos(ang) * 72.5, y: sin(ang) * 72.5)
            }
            if let icono = icono {
                Image(nsImage: icono).resizable().interpolation(.high).frame(width: 86, height: 86)
                    .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                    .offset(y: av.estado == "instalando" ? sin(t * 1.7) * 2 : 0)
            }
            if av.estado != "instalando" {
                Circle().fill(colorEstado).frame(width: 32, height: 32)
                    .overlay(Circle().stroke(Color(hex: 0x120d0f), lineWidth: 3))
                    .overlay(av.estado == "listo"
                             ? AnyView(Image(systemName: "checkmark").font(.system(size: 14, weight: .heavy)).foregroundColor(.white))
                             : AnyView(Text("!").font(.system(size: 19, weight: .black)).foregroundColor(.white)))
                    .offset(x: 40, y: 40)
            }
        }
    }

    // ---- textos (pocos: el anillo ya cuenta el avance)
    var titulo: some View {
        Text(av.estado == "listo" ? "¡Listo!" : (av.estado == "error" ? "No se pudo instalar" : "Instalando"))
            .font(.system(size: 22, weight: .semibold)).foregroundColor(TEXTO).lineLimit(1)
    }

    // solo si hay algo que decir: el error, o un aviso mientras instala
    @ViewBuilder var detalle: some View {
        if av.estado == "error" {
            Text(av.mensaje).font(.system(size: 13, weight: .medium)).foregroundColor(ERROR)
                .multilineTextAlignment(.center).lineLimit(3).fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity)
        } else if av.estado == "instalando" && !av.aviso.isEmpty {
            Text(av.aviso).font(.system(size: 13, weight: .medium)).foregroundColor(AMBAR.opacity(0.9))
                .multilineTextAlignment(.center).lineLimit(2).frame(maxWidth: .infinity)
        }
    }

    @ViewBuilder var cifra: some View {
        if av.estado == "instalando" {
            Text("\(Int(av.valor.rounded())) %").font(.system(size: 17, weight: .medium)).monospacedDigit()
                .foregroundColor(SUAVE)
        }
    }

    @ViewBuilder var pie: some View {
        if av.estado == "error" {
            Button("Cerrar", action: cerrar).buttonStyle(BotonPildora())
        }
    }
}

// ---------------------------------------------------------------------------------------------------------------- app
final class VentanaSinMarco: NSWindow {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

final class Instalador: NSObject, NSApplicationDelegate {
    let av = Avance()
    var ventana: NSWindow?
    var reloj: Timer?
    var antes = Date()
    var terminado = false
    var copiando = ""                 // «….app.nuevo» mientras se copia (se borra si se cierra a medias)
    var demo: [(Double, String, String)] = []
    var tDemo = Date()
    let args = CommandLine.arguments
    var esDemo: Bool { args.contains("--demo") || args.contains("--demo-error") }
    lazy var recursos = Bundle.main.resourcePath ?? "."
    lazy var version = (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String) ?? "?"

    func applicationDidFinishLaunching(_ n: Notification) {
        // ya instalado (igual o más nuevo): solo se abre el programa (y se expulsa el disco, que ya no hace falta)
        if !esDemo, let app = appInstalada(), numeroVersion(versionDe(app) ?? "0") >= numeroVersion(version) {
            abrir(app)
            expulsarDisco()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { NSApp.terminate(nil) }
            return
        }
        let icono = NSImage(contentsOfFile: recursos + "/icono.png") ?? NSApp.applicationIconImage
        let vista = VistaInstalador(av: av, version: version, icono: icono, cerrar: { NSApp.terminate(nil) })
        let w = VentanaSinMarco(contentRect: NSRect(x: 0, y: 0, width: ANCHO, height: ALTO), styleMask: [.borderless],
                                backing: .buffered, defer: false)
        w.isOpaque = false
        w.backgroundColor = .clear
        w.hasShadow = true
        w.isMovableByWindowBackground = true
        w.title = "Instalar Comprobantes"
        w.contentView = NSHostingView(rootView: vista)
        w.center()
        w.makeKeyAndOrderFront(nil)
        ventana = w
        NSApp.activate(ignoringOtherApps: true)
        if esDemo { empezarDemo() } else { empezar() }
        antes = Date()
        reloj = Timer.scheduledTimer(withTimeInterval: 1.0 / 60.0, repeats: true) { [weak self] _ in self?.tic() }
    }

    // ⌘Q siempre: la copia a medias (….app.nuevo) se borra y la instalada sigue como estaba
    func applicationShouldTerminate(_ s: NSApplication) -> NSApplication.TerminateReply { .terminateNow }

    func applicationWillTerminate(_ n: Notification) {
        if !copiando.isEmpty { try? FileManager.default.removeItem(atPath: copiando) }
    }

    func enviar(_ tipo: String, _ texto: String = "") {
        DispatchQueue.main.async { self.av.evento(tipo, texto) }
    }

    // ---- la instalación de verdad (en segundo plano: la ventana sigue animada)
    func empezar() {
        DispatchQueue.global(qos: .userInitiated).async { [self] in
            let fm = FileManager.default
            Thread.sleep(forTimeInterval: 0.3)
            enviar("PASO", "1")
            guard let paquete = buscarPaquete(version) else {
                enviar("FALLO", "No encontré el programa en el disco. Vuelve a abrir el .dmg descargado."); return
            }
            ejecutar("/usr/bin/pkill", ["-f", APP + "/Contents/MacOS/"])        // si estaba abierto (actualización)
            // /Applications si se puede escribir ahí (y cambiar la anterior); si no, ~/Applications: nunca pide contraseña
            var carpeta = "/Applications"
            let previa = carpeta + "/" + APP
            if !fm.isWritableFile(atPath: carpeta) || (fm.fileExists(atPath: previa) && !fm.isWritableFile(atPath: previa)) {
                carpeta = HOME + "/Applications"
                try? fm.createDirectory(atPath: carpeta, withIntermediateDirectories: true)
            }
            let destino = carpeta + "/" + APP
            let nuevo = destino + ".nuevo"
            try? fm.removeItem(atPath: nuevo)
            let total = megas(paquete)
            DispatchQueue.main.async { self.av.mbTotal = total }
            copiando = nuevo
            var copiado = false
            DispatchQueue.global(qos: .utility).async { [self] in            // los MB copiados, para el anillo
                while !copiado {
                    let hecho = megas(nuevo)
                    DispatchQueue.main.async { self.av.mbHecho = hecho }
                    Thread.sleep(forTimeInterval: 0.35)
                }
            }
            let (st, salida) = ejecutar("/usr/bin/ditto", ["--noqtn", paquete, nuevo])
            copiado = true
            guard st == 0, esApp(nuevo) else {
                try? fm.removeItem(atPath: nuevo); copiando = ""
                enviar("FALLO", "No se pudo copiar a Aplicaciones: " + salida.trimmingCharacters(in: .whitespacesAndNewlines))
                return
            }
            DispatchQueue.main.async { self.av.mbHecho = total }
            if fm.fileExists(atPath: destino) {
                do { try fm.removeItem(atPath: destino) } catch {
                    try? fm.removeItem(atPath: nuevo); copiando = ""
                    enviar("FALLO", "No se pudo reemplazar la versión anterior: ciérrala y vuelve a intentar."); return
                }
            }
            do { try fm.moveItem(atPath: nuevo, toPath: destino) } catch {
                copiando = ""
                enviar("FALLO", "No se pudo terminar de copiar: " + error.localizedDescription); return
            }
            copiando = ""
            ejecutar("/usr/bin/xattr", ["-dr", "com.apple.quarantine", destino])
            // 2) el Dock
            enviar("PASO", "2")
            let (_, dock) = ejecutar("/usr/bin/defaults", ["read", "com.apple.dock", "persistent-apps"])
            if !dock.contains(APP) {
                let entrada = "<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>\(destino)</string>"
                    + "<key>_CFURLStringType</key><integer>0</integer></dict></dict></dict>"
                let (sd, _) = ejecutar("/usr/bin/defaults", ["write", "com.apple.dock", "persistent-apps", "-array-add", entrada])
                ejecutar("/usr/bin/killall", ["Dock"])
                if sd != 0 { enviar("AVISO", "No se pudo fijar en el Dock: arrástralo tú desde Aplicaciones") }
            }
            Thread.sleep(forTimeInterval: 0.3)
            enviar("FIN", version)
        }
    }

    func tic() {
        let ahora = Date()
        let dt = min(0.1, max(0, ahora.timeIntervalSince(antes)))
        antes = ahora
        if esDemo { alimentarDemo() }
        av.avanzar(dt)
        if av.estado == "listo" && !terminado && !esDemo {
            terminado = true
            // Comprobantes YA: un instante para ver el ✓ y se abre; el instalador se cierra y el disco se expulsa
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.45) { self.abrirYSalir() }
        }
    }

    func abrirYSalir() {
        if let app = appInstalada() { abrir(app) }
        expulsarDisco()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { NSApp.terminate(nil) }
    }

    // el disco del que vino, cuando este instalador ya se cerró (un proceso aparte que espera; si sigue ocupado, insiste y
    // al final a la fuerza: con la ventana del disco abierta en el Finder, el primer intento sale «ocupado»)
    func expulsarDisco() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/sh")
        p.arguments = ["-c", """
            sleep 2
            for i in 1 2 3 4 5; do
              listo=1
              for v in /Volumes/Comprobantes*; do
                [ -d "$v/Instalar Comprobantes.app" ] || continue
                /usr/bin/hdiutil detach "$v" -quiet || listo=0
              done
              [ $listo = 1 ] && exit 0
              sleep 2
            done
            for v in /Volumes/Comprobantes*; do [ -d "$v/Instalar Comprobantes.app" ] && /usr/bin/hdiutil detach "$v" -force -quiet; done
            exit 0
            """]
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        try? p.run()
    }

    // ---- simulación (--demo / --demo-error)
    func empezarDemo() {
        tDemo = Date()
        av.mbTotal = 340
        demo = [(0.3, "PASO", "1")]
        if args.contains("--demo-error") {
            demo.append((2.6, "FALLO", "No se pudo copiar a Aplicaciones: no hay espacio en el disco."))
        } else {
            demo += [(3.4, "PASO", "2"), (4.2, "FIN", version)]
        }
    }

    func alimentarDemo() {
        let k = Date().timeIntervalSince(tDemo)
        if av.paso == 1 && av.estado == "instalando" { av.mbHecho = min(av.mbTotal, max(0, (k - 0.3) / 3.0 * av.mbTotal)) }
        while let e = demo.first, e.0 <= k {
            demo.removeFirst()
            av.evento(e.1, e.2)
        }
    }
}

@main
struct Principal {
    static func main() {
        let app = NSApplication.shared
        let delegado = Instalador()
        app.delegate = delegado
        app.setActivationPolicy(.regular)
        app.run()
    }
}
