// =============================================================================================================================
// Contents/MacOS/instalar de "Instalar Comprobantes.app" (la app del DMG): la ventana del instalador, NATIVA (AppKit + SwiftUI),
// con el mismo esquema que el instalador de CineSlide: aparece al instante con el doble clic, muestra los pasos con una barra
// de progreso y, al terminar, abre Comprobantes Cinema, se cierra y expulsa el disco.
// - Si Comprobantes Cinema ya está instalado con la misma versión o una más nueva, solo lo abre.
// - Pasos: 1) copiar el programa a Aplicaciones (o a ~/Aplicaciones si no hay permiso), 2) fijarlo en el Dock,
//   3) revisar que PhotoCraft esté instalado (si falta, avisa: el programa lo necesita para crear los comprobantes).
//   instalar --demo | --demo-error      simula una instalación (para ver el diseño y sacar capturas)
// Lo compila empaquetar/mac/construir_dmg.py en una Mac (swiftc, arm64 + x86_64 con lipo); Windows no puede.
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

let ROJO = Color(hex: 0xe0262b), CORAL = Color(hex: 0xff5a5f), NARANJA = Color(hex: 0xff9a3d)
let TEXTO = Color(hex: 0xf6f2f2), SUAVE = Color(hex: 0xbdb3b3), TENUE = Color(hex: 0x716868)
let VERDE = Color(hex: 0x3ed392), ERROR = Color(hex: 0xff6b6b), AMBAR = Color(hex: 0xffc46b)
let NOMBRE = "Comprobantes Cinema"
let APP = "Comprobantes Cinema.app"
let BENEFICIOS = ["Un solo doble clic", "No necesita internet", "No pide contraseña"]
let PASOS = ["Programa Comprobantes", "App en Aplicaciones y en el Dock", "PhotoCraft (para crear los comprobantes)"]
// porcentaje al empezar y al terminar cada paso (0 = preparar) y segundos típicos: dentro de un paso la barra avanza sola
let TRAMOS: [(Double, Double)] = [(0, 4), (4, 82), (82, 92), (92, 99)]
let DURACION: [Double] = [0.6, 9, 1.2, 0.8]

let HOME = NSHomeDirectory()

func numeroVersion(_ v: String) -> Int {
    let p = v.split(separator: ".").map { Int($0) ?? 0 }
    return (p.count > 0 ? p[0] : 0) * 1_000_000 + (p.count > 1 ? p[1] : 0) * 1_000 + (p.count > 2 ? p[2] : 0)
}

func versionDe(_ app: String) -> String? {
    NSDictionary(contentsOfFile: app + "/Contents/Info.plist")?["CFBundleShortVersionString"] as? String
}

func appInstalada() -> String? {
    for ruta in ["/Applications/" + APP, HOME + "/Applications/" + APP] where FileManager.default.fileExists(atPath: ruta) {
        return ruta
    }
    return nil
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

// ---------------------------------------------------------------------------------------------------------------- avance
final class Avance: ObservableObject {
    @Published var paso = 0
    @Published var detalles = Array(repeating: [String](), count: 4)
    @Published var avisos = Array(repeating: "", count: 4)
    @Published var estado = "instalando"           // instalando | listo | error
    @Published var mensaje = ""
    @Published var valor: Double = 0
    var tPaso = Date()
    var tEstado = Date()

    func evento(_ tipo: String, _ texto: String = "") {
        guard estado == "instalando" else { return }
        switch tipo {
        case "PASO":
            if let n = Int(texto), n > paso { paso = n; tPaso = Date() }
        case "OK":
            if !texto.isEmpty { detalles[paso].append(texto.replacingOccurrences(of: HOME, with: "~")) }
        case "AVISO":
            if !texto.isEmpty { avisos[paso] = texto }
        case "FALLO":
            estado = "error"; mensaje = texto.isEmpty ? "Algo salió mal." : texto; tEstado = Date()
        case "FIN":
            estado = "listo"; tEstado = Date()
        default:
            break
        }
    }

    func objetivo() -> Double {
        if estado == "listo" { return 100 }
        let i = min(max(paso, 0), 3)
        let (a, b) = TRAMOS[i]
        let k = Date().timeIntervalSince(tPaso)
        return a + (b - a) * min(1, 0.9 * (1 - exp(-k / DURACION[i])))
    }

    func avanzar(_ dt: Double) {
        let obj = objetivo()
        valor += (obj - valor) * min(1, dt * (estado == "listo" ? 5 : 2.4))
    }
}

// ---------------------------------------------------------------------------------------------------------------- vista
struct BotonPildora: ButtonStyle {
    var principal = true
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 14, weight: principal ? .bold : .semibold))
            .foregroundColor(.white)
            .padding(.horizontal, 26).frame(height: 44)
            .background(
                Group {
                    if principal {
                        Capsule().fill(LinearGradient(colors: [CORAL, ROJO, NARANJA], startPoint: .leading, endPoint: .trailing))
                    } else {
                        Capsule().fill(Color.white.opacity(0.06)).overlay(Capsule().stroke(Color(hex: 0x4a3434), lineWidth: 1))
                    }
                }
            )
            .opacity(configuration.isPressed ? 0.8 : 1)
    }
}

struct VistaInstalador: View {
    @ObservedObject var av: Avance
    let version: String
    let mac: String
    let icono: NSImage?
    let cerrar: () -> Void

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { ctx in
            let t = ctx.date.timeIntervalSinceReferenceDate
            HStack(spacing: 0) {
                heroe(t)
                columna(t)
                    .padding(.leading, 46).padding(.trailing, 44).padding(.top, 46).padding(.bottom, 34)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            }
            .frame(width: 900, height: 520)
            .background(LinearGradient(colors: [Color(hex: 0x1b1515), Color(hex: 0x0c0909)], startPoint: .topLeading,
                                       endPoint: .bottomTrailing))
            .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).stroke(colorBorde, lineWidth: 1.2))
        }
    }

    var colorEstado: Color { av.estado == "listo" ? VERDE : (av.estado == "error" ? ERROR : ROJO) }
    var colorBorde: Color {
        av.estado == "listo" ? VERDE.opacity(0.6) : (av.estado == "error" ? ERROR.opacity(0.6) : Color(hex: 0x3d2a2a))
    }

    // ---- panel de la izquierda
    func heroe(_ t: Double) -> some View {
        ZStack {
            LinearGradient(colors: [Color(hex: 0x4c0f13), Color(hex: 0x25110f), Color(hex: 0x120c0c)], startPoint: .topLeading,
                           endPoint: .bottomTrailing)
            luz(ROJO, 0.25, 0.20, 264, 0.21, 0, t)
            luz(NARANJA, 0.85, 0.80, 280, 0.17, 1, t)
            luz(CORAL, 0.55, 0.50, 182, 0.13, 2, t)
            VStack(spacing: 0) {
                Spacer().frame(height: 70)
                emblema(t)
                Text("Comprobantes").font(.system(size: 28, weight: .bold)).foregroundColor(TEXTO).padding(.top, 8)
                Text("CINEMA PRODUCTIONS").font(.system(size: 10, weight: .bold)).tracking(2.5)
                    .foregroundColor(TEXTO.opacity(0.6)).padding(.top, 4)
                Text("INSTALADOR  ·  v\(version)").font(.system(size: 11, weight: .bold)).tracking(3)
                    .foregroundColor(CORAL.opacity(0.95)).padding(.top, 10)
                Spacer()
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(BENEFICIOS, id: \.self) { b in
                        HStack(spacing: 10) {
                            Circle().fill(CORAL.opacity(0.2)).frame(width: 20, height: 20)
                                .overlay(Image(systemName: "checkmark").font(.system(size: 9, weight: .heavy)).foregroundColor(CORAL))
                            Text(b).font(.system(size: 13, weight: .semibold)).foregroundColor(TEXTO.opacity(0.88))
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading).padding(.leading, 40).padding(.bottom, 34)
            }
        }
        .frame(width: 330, height: 520)
        .clipped()
        .overlay(Rectangle().fill(LinearGradient(colors: [CORAL.opacity(0), CORAL.opacity(0.35), CORAL.opacity(0)], startPoint: .top,
                                                 endPoint: .bottom)).frame(width: 1).padding(.vertical, 24),
                 alignment: .trailing)
    }

    func luz(_ c: Color, _ fx: Double, _ fy: Double, _ r: Double, _ vel: Double, _ i: Double, _ t: Double) -> some View {
        Circle()
            .fill(RadialGradient(colors: [c.opacity(0.26), c.opacity(0)], center: .center, startRadius: 0, endRadius: r))
            .frame(width: r * 2, height: r * 2)
            .position(x: 330 * (fx + 0.12 * sin(t * vel * 2 + i)), y: 520 * (fy + 0.08 * cos(t * vel * 1.6 + i * 2)))
    }

    func emblema(_ t: Double) -> some View {
        let instalando = av.estado == "instalando"
        let ang = (t * (instalando ? 300 : 60)).truncatingRemainder(dividingBy: 360)
        let k = Date().timeIntervalSince(av.tEstado)
        let pulso = instalando ? 0.75 + 0.25 * sin(t * 2.2) : 1 + 0.8 * exp(-k * 2.2)
        let paradas: [Gradient.Stop]
        if instalando {
            paradas = [Gradient.Stop(color: CORAL, location: 0), Gradient.Stop(color: ROJO.opacity(0.7), location: 0.18),
                       Gradient.Stop(color: NARANJA.opacity(0), location: 0.38), Gradient.Stop(color: NARANJA.opacity(0), location: 0.7),
                       Gradient.Stop(color: NARANJA.opacity(0.9), location: 1)]
        } else {
            paradas = [Gradient.Stop(color: colorEstado, location: 0), Gradient.Stop(color: colorEstado.opacity(0.55), location: 0.5),
                       Gradient.Stop(color: colorEstado, location: 1)]
        }
        return ZStack {
            Circle().fill(RadialGradient(colors: [colorEstado.opacity(min(1, 0.34 * pulso)), colorEstado.opacity(0)],
                                         center: .center, startRadius: 0, endRadius: 138))
                .frame(width: 276, height: 276)
            Circle().fill(Color(hex: 0x140c0c, a: 0.94)).frame(width: 120, height: 120)
                .overlay(Circle().stroke(Color.white.opacity(0.1), lineWidth: 1))
            Circle()
                .stroke(AngularGradient(gradient: Gradient(stops: paradas), center: .center),
                        style: StrokeStyle(lineWidth: 4, lineCap: .round))
                .frame(width: 138, height: 138)
                .rotationEffect(.degrees(ang))
            ForEach(0..<3, id: \.self) { i in
                let a = (-ang * 0.55 + Double(i) * 120) * .pi / 180
                Circle().fill((instalando ? [NARANJA, CORAL, ROJO][i] : colorEstado).opacity(0.8)).frame(width: 6, height: 6)
                    .offset(x: cos(a) * 84, y: sin(a) * 84)
            }
            Group {
                if let icono = icono {
                    Image(nsImage: icono).resizable().interpolation(.high).frame(width: 96, height: 96)
                }
            }
            .offset(y: sin(t * 1.7) * 2.5)
            if !instalando {
                Circle().fill(colorEstado).frame(width: 34, height: 34)
                    .overlay(Circle().stroke(Color(hex: 0x140c0c), lineWidth: 3))
                    .overlay(av.estado == "listo"
                             ? AnyView(Image(systemName: "checkmark").font(.system(size: 15, weight: .heavy)).foregroundColor(.white))
                             : AnyView(Text("!").font(.system(size: 20, weight: .black)).foregroundColor(.white)))
                    .offset(x: 41, y: 41)
            }
        }
        .frame(width: 180, height: 180)
    }

    // ---- columna de la derecha
    var titulo: String {
        av.estado == "listo" ? "¡Comprobantes está listo!" : (av.estado == "error" ? "No se pudo instalar" : "Instalando Comprobantes")
    }
    var subtitulo: String {
        av.estado == "listo" ? "Se instaló la versión \(version). Lo encuentras en Aplicaciones, en el Dock y en Launchpad."
            : (av.estado == "error" ? av.mensaje : "Versión \(version) para \(mac)")
    }
    var accion: String {
        if av.estado == "listo" { return "Instalación completa" }
        if av.estado == "error" { return "Se detuvo en: \(PASOS[max(0, av.paso - 1)])" }
        if av.paso == 0 { return "Preparando el instalador…" }
        return "Paso \(av.paso) de \(PASOS.count) · \(PASOS[av.paso - 1])"
    }

    func columna(_ t: Double) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(titulo).font(.system(size: 30, weight: .bold)).foregroundColor(TEXTO).lineLimit(1)
            Text(subtitulo).font(.system(size: 14)).foregroundColor(av.estado == "error" ? ERROR : SUAVE)
                .lineLimit(2).frame(height: 40, alignment: .topLeading).padding(.top, 6)
            HStack {
                Text(accion).font(.system(size: 13, weight: .semibold)).foregroundColor(SUAVE).lineLimit(1)
                Spacer()
                Text("\(Int(av.valor.rounded())) %").font(.system(size: 15, weight: .bold)).monospacedDigit().foregroundColor(TEXTO)
            }
            .padding(.top, 14)
            barra(t).padding(.top, 10)
            VStack(spacing: 0) {
                ForEach(1...PASOS.count, id: \.self) { i in fila(i, t) }
            }
            .padding(.top, 22)
            Spacer(minLength: 0)
            pie()
        }
    }

    var rellenoBarra: LinearGradient {
        let colores: [Color]
        if av.estado == "listo" {
            colores = [Color(hex: 0x23a86e), Color(hex: 0x5fd6a0)]
        } else if av.estado == "error" {
            colores = [Color(hex: 0xc2444a), ERROR]
        } else {
            colores = [CORAL, ROJO, NARANJA]
        }
        return LinearGradient(colors: colores, startPoint: .leading, endPoint: .trailing)
    }

    func barra(_ t: Double) -> some View {
        GeometryReader { g in
            let w: CGFloat = max(10, g.size.width * CGFloat(min(100, av.valor)) / 100)
            ZStack(alignment: .leading) {
                Capsule().fill(Color.white.opacity(0.07)).frame(height: 10)
                Capsule().fill(rellenoBarra).frame(width: w, height: 10)
            }
            .frame(height: 10)
            .overlay(alignment: .leading) {
                if av.estado == "instalando" {
                    Circle().fill(RadialGradient(colors: [NARANJA.opacity(0.55), NARANJA.opacity(0)], center: .center, startRadius: 0,
                                                 endRadius: 16))
                        .frame(width: 32, height: 32).offset(x: w - 19)
                }
            }
        }
        .frame(height: 10)
    }

    func fila(_ i: Int, _ t: Double) -> some View {
        let hecho = av.estado == "listo" || i < av.paso
        let actual = av.estado != "listo" && i == av.paso
        var detalle = "", colorDetalle = TENUE
        if !av.avisos[i].isEmpty {
            detalle = av.avisos[i]; colorDetalle = AMBAR.opacity(0.9)
        } else if hecho && !av.detalles[i].isEmpty {
            detalle = av.detalles[i].suffix(2).joined(separator: " · ")
        }
        let nombre = i == 1 ? "Programa Comprobantes \(version)" : PASOS[i - 1]
        return HStack(spacing: 12) {
            ZStack {
                if hecho && av.avisos[i].isEmpty {
                    Circle().fill(LinearGradient(colors: [CORAL, ROJO], startPoint: .topLeading, endPoint: .bottomTrailing))
                    Image(systemName: "checkmark").font(.system(size: 10, weight: .heavy)).foregroundColor(.white)
                } else if hecho {
                    Circle().fill(AMBAR)
                    Text("!").font(.system(size: 13, weight: .black)).foregroundColor(Color(hex: 0x2a1d08))
                } else if actual && av.estado == "error" {
                    Circle().fill(ERROR)
                    Text("!").font(.system(size: 13, weight: .black)).foregroundColor(.white)
                } else if actual {
                    Circle().stroke(CORAL.opacity(0.22), lineWidth: 2.4).frame(width: 19, height: 19)
                    Circle().trim(from: 0, to: 0.28).stroke(CORAL, style: StrokeStyle(lineWidth: 2.6, lineCap: .round))
                        .frame(width: 19, height: 19).rotationEffect(.degrees((t * 420).truncatingRemainder(dividingBy: 360)))
                } else {
                    Circle().stroke(TENUE.opacity(0.7), lineWidth: 1.6).frame(width: 18, height: 18)
                }
            }
            .frame(width: 22, height: 22)
            Text(nombre).font(.system(size: 14, weight: actual ? .semibold : .regular))
                .foregroundColor(hecho || actual ? TEXTO : TENUE).lineLimit(1).layoutPriority(1)
            Spacer(minLength: 12)
            Text(detalle).font(.system(size: 12)).foregroundColor(colorDetalle).lineLimit(1).truncationMode(.tail)
        }
        .frame(height: 38)
    }

    @ViewBuilder func pie() -> some View {
        if av.estado == "error" {
            HStack(spacing: 12) {
                Button("Cerrar", action: cerrar).buttonStyle(BotonPildora(principal: true))
                Text("Ábrelo otra vez; si se repite, avísanos.").font(.system(size: 12)).foregroundColor(TENUE).padding(.leading, 6)
            }
        } else if av.estado == "listo" {
            Text("Abriendo Comprobantes…").font(.system(size: 14, weight: .semibold)).foregroundColor(VERDE)
        } else {
            Text("Puedes seguir usando tu Mac. Al terminar, Comprobantes se abre solo.").font(.system(size: 13)).foregroundColor(TENUE)
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
    var demo: [(Double, String, String)] = []
    var tDemo = Date()
    var destino = ""
    let args = CommandLine.arguments
    var esDemo: Bool { args.contains("--demo") || args.contains("--demo-error") }
    lazy var recursos = Bundle.main.resourcePath ?? "."
    lazy var paquete = recursos + "/" + APP
    lazy var version = versionDe(paquete) ?? ((Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String) ?? "?")

    func applicationDidFinishLaunching(_ n: Notification) {
        // ya instalado (igual o más nuevo): solo se abre el programa
        if !esDemo, let app = appInstalada(), let inst = versionDe(app), numeroVersion(inst) >= numeroVersion(version) {
            NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: app), configuration: NSWorkspace.OpenConfiguration()) { _, _ in
                DispatchQueue.main.async { self.expulsarDisco(); NSApp.terminate(nil) }
            }
            return
        }
        #if arch(arm64)
        let mac = "Mac con Apple Silicon"
        #else
        let mac = "Mac con procesador Intel"
        #endif
        let icono = NSImage(contentsOfFile: recursos + "/icono.png") ?? NSApp.applicationIconImage
        let vista = VistaInstalador(av: av, version: version, mac: mac, icono: icono, cerrar: { NSApp.terminate(nil) })
        let w = VentanaSinMarco(contentRect: NSRect(x: 0, y: 0, width: 900, height: 520), styleMask: [.borderless],
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
        reloj = Timer.scheduledTimer(withTimeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in self?.tic() }
    }

    func applicationShouldTerminate(_ s: NSApplication) -> NSApplication.TerminateReply {
        // no se cierra a media instalación (sin ventana = ya estaba instalado y solo se abrió el programa)
        (ventana != nil && av.estado == "instalando" && !esDemo) ? .terminateCancel : .terminateNow
    }

    func enviar(_ tipo: String, _ texto: String = "") {
        DispatchQueue.main.async { self.av.evento(tipo, texto) }
    }

    // ---- la instalación de verdad (en segundo plano: la ventana sigue animada)
    func empezar() {
        DispatchQueue.global(qos: .userInitiated).async { [self] in
            let fm = FileManager.default
            Thread.sleep(forTimeInterval: 0.4)
            // 1) programa en Aplicaciones
            enviar("PASO", "1")
            guard fm.fileExists(atPath: paquete) else {
                enviar("FALLO", "Falta el programa dentro del instalador. Descarga el instalador otra vez."); return
            }
            ejecutar("/usr/bin/pkill", ["-f", APP + "/Contents/MacOS/"])        // si estaba abierto (actualización)
            var carpeta = "/Applications"
            if !fm.isWritableFile(atPath: carpeta) {
                carpeta = HOME + "/Applications"
                try? fm.createDirectory(atPath: carpeta, withIntermediateDirectories: true)
            }
            destino = carpeta + "/" + APP
            if fm.fileExists(atPath: destino) { try? fm.removeItem(atPath: destino) }
            let (st, salida) = ejecutar("/usr/bin/ditto", ["--noqtn", paquete, destino])
            guard st == 0, fm.fileExists(atPath: destino) else {
                enviar("FALLO", "No se pudo copiar a Aplicaciones: " + salida.trimmingCharacters(in: .whitespacesAndNewlines)); return
            }
            enviar("OK", destino)
            // 2) Dock
            enviar("PASO", "2")
            let (_, dock) = ejecutar("/usr/bin/defaults", ["read", "com.apple.dock", "persistent-apps"])
            if dock.lowercased().contains("comprobantes") {
                enviar("OK", "Ya estaba en el Dock")
            } else {
                let entrada = "<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>\(destino)</string>"
                    + "<key>_CFURLStringType</key><integer>0</integer></dict></dict></dict>"
                let (sd, _) = ejecutar("/usr/bin/defaults", ["write", "com.apple.dock", "persistent-apps", "-array-add", entrada])
                ejecutar("/usr/bin/killall", ["Dock"])
                if sd == 0 { enviar("OK", "Fijado en el Dock") } else { enviar("AVISO", "No se pudo fijar en el Dock (arrástralo tú)") }
            }
            // 3) PhotoCraft
            enviar("PASO", "3")
            let candidatos = (try? fm.contentsOfDirectory(atPath: "/Applications")) ?? []
            let hay = candidatos.contains { $0.lowercased().contains("photocraft") || $0.lowercased().contains("artcraft") }
            if hay { enviar("OK", "PhotoCraft encontrado") } else { enviar("AVISO", "Falta PhotoCraft: instálalo para crear los comprobantes") }
            Thread.sleep(forTimeInterval: 0.5)
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
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) { self.abrirYSalir() }
        }
    }

    // ---- al terminar: abre el programa, el instalador se cierra y el disco se expulsa
    func abrirYSalir() {
        if let app = appInstalada() {
            NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: app), configuration: NSWorkspace.OpenConfiguration()) { _, _ in }
        }
        expulsarDisco()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { NSApp.terminate(nil) }
    }

    func expulsarDisco() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/sh")
        p.arguments = ["-c", "sleep 3; for v in /Volumes/Comprobantes*; do [ -d \"$v/Instalar Comprobantes.app\" ] && /usr/bin/hdiutil detach \"$v\" -quiet; done; exit 0"]
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        try? p.run()
    }

    // ---- simulación (--demo / --demo-error)
    func empezarDemo() {
        tDemo = Date()
        demo = [(0.4, "PASO", "1"), (2.6, "OK", "/Applications/" + APP), (2.8, "PASO", "2"), (3.6, "OK", "Fijado en el Dock")]
        if args.contains("--demo-error") {
            demo.append((4.2, "FALLO", "No se pudo copiar a Aplicaciones: no hay espacio en el disco."))
        } else {
            demo += [(3.8, "PASO", "3"), (4.4, "AVISO", "Falta PhotoCraft: instálalo para crear los comprobantes"), (5.0, "FIN", version)]
        }
    }

    func alimentarDemo() {
        let k = Date().timeIntervalSince(tDemo)
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
