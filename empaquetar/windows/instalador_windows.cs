// =============================================================================================================================
// Instalador de Windows de Comprobantes Cinema Productions, con el mismo método que el de CineSlide: un .exe propio
// (C# + WinForms sobre el .NET Framework 4 que ya trae Windows) con el programa en un .zip pegado al final del archivo.
// Doble clic → ventana con pasos y barra de progreso → instala en %LOCALAPPDATA%\Programs (no pide permisos), instala las
// fuentes del diseño, crea los accesos directos y la entrada de «Aplicaciones instaladas», abre el programa y se cierra.
// Si ya está instalada la misma versión (o una más nueva), solo abre el programa.
//   /reparar                        instala aunque ya esté la misma versión
//   /silencioso                     sin ventana (pruebas); con /desinstalar quita el programa sin preguntar
//   /desinstalar                    lo usa «Aplicaciones instaladas» (Desinstalar Comprobantes.exe, en la carpeta del programa)
//   /demo  /demo-error              simula una instalación para ver el diseño (no instala nada)
//   /captura=<png> /en=<segundos>   guarda una imagen de la ventana (con /demo, después se cierra)
// Formato: [este .exe][paquete .zip][Int64 posición del zip][8 bytes "CCPAQ001"].
// Lo compila windows\construir_instalador.ps1 con el csc.exe de .NET Framework (C# 5) junto con version.cs (VersionApp.V).
// =============================================================================================================================
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

static class Inst
{
    public const string NOMBRE = "Comprobantes Cinema Productions";
    public const string EXE = "Comprobantes Cinema.exe";
    public const string DESINSTALADOR = "Desinstalar Comprobantes.exe";
    public const string FIRMA = "CCPAQ001";
    public const string CLAVE = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\ComprobantesCinemaProductions";
    public const string CLAVE_INNO = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\{4F5098BC-D578-40A3-8BDB-5CCAD9D12264}_is1";
    public const string CLAVE_FUENTES = @"Software\Microsoft\Windows NT\CurrentVersion\Fonts";
    public static readonly string LOCAL = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
    public static readonly string CARPETA = Path.Combine(Path.Combine(LOCAL, "Programs"), NOMBRE);
    public static readonly string[] PASOS = { "Programa Comprobantes", "Fuentes del diseño", "Accesos directos",
                                              "Comprobación final" };

    public static string ExeInstalado { get { return Path.Combine(CARPETA, EXE); } }
    public static string AccesoEscritorio
    {
        get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), NOMBRE + ".lnk"); }
    }
    public static string AccesoInicio
    {
        get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), NOMBRE + ".lnk"); }
    }

    public static long NumeroVersion(string v)
    {
        if (string.IsNullOrEmpty(v)) return -1;
        string[] p = v.Split('.');
        long n = 0;
        for (int i = 0; i < 3; i++)
        {
            int x = 0;
            if (i < p.Length) int.TryParse(p[i], out x);
            n = n * 1000 + x;
        }
        return n;
    }

    public static string VersionInstalada()
    {
        using (RegistryKey k = Registry.CurrentUser.OpenSubKey(CLAVE))
        {
            return k == null ? null : k.GetValue("DisplayVersion") as string;
        }
    }

    // Cierra Comprobantes si está abierto desde la carpeta instalada (al actualizar)
    public static void CerrarPrograma()
    {
        foreach (Process p in Process.GetProcessesByName(Path.GetFileNameWithoutExtension(EXE)))
        {
            try
            {
                string f = p.MainModule.FileName;
                if (!f.StartsWith(CARPETA + "\\", StringComparison.OrdinalIgnoreCase)) continue;
                p.CloseMainWindow();
                if (!p.WaitForExit(2500)) { p.Kill(); p.WaitForExit(5000); }
            }
            catch { }
            finally { p.Dispose(); }
        }
    }

    public static void Abrir(string exe)
    {
        try
        {
            var psi = new ProcessStartInfo(exe);
            psi.WorkingDirectory = Path.GetDirectoryName(exe);
            psi.UseShellExecute = true;
            Process.Start(psi);
        }
        catch { }
    }

    public static void BorrarCarpeta(string dir)
    {
        for (int intento = 0; intento < 4; intento++)
        {
            try
            {
                if (Directory.Exists(dir)) Directory.Delete(dir, true);
                return;
            }
            catch (Exception)
            {
                if (intento == 3) throw;
                Thread.Sleep(600);
            }
        }
    }

    public static void BorrarArchivo(string f)
    {
        for (int intento = 0; intento < 4; intento++)
        {
            try
            {
                if (File.Exists(f)) { File.SetAttributes(f, FileAttributes.Normal); File.Delete(f); }
                return;
            }
            catch (Exception)
            {
                if (intento == 3) throw;
                Thread.Sleep(600);
            }
        }
    }

    [DllImport("gdi32.dll", CharSet = CharSet.Unicode)] public static extern int AddFontResource(string archivo);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, int msg, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}

// ---------------------------------------------------------------------------------------------------------- el paquete .zip
class Paquete
{
    public string Exe;
    public long Inicio;
    public long Largo;

    public static Paquete Abrir(string exe)
    {
        try
        {
            using (var fs = new FileStream(exe, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            {
                if (fs.Length < 32) return null;
                fs.Seek(-16, SeekOrigin.End);
                var b = new byte[16];
                int leidos = 0;
                while (leidos < 16)
                {
                    int n = fs.Read(b, leidos, 16 - leidos);
                    if (n <= 0) return null;
                    leidos += n;
                }
                if (Encoding.ASCII.GetString(b, 8, 8) != Inst.FIRMA) return null;
                long pos = BitConverter.ToInt64(b, 0);
                if (pos <= 0 || pos >= fs.Length - 16) return null;
                var p = new Paquete();
                p.Exe = exe;
                p.Inicio = pos;
                p.Largo = fs.Length - 16 - pos;
                return p;
            }
        }
        catch { return null; }
    }
}

// Un pedazo de un archivo visto como si fuera un archivo aparte (para leer el .zip sin copiarlo)
class Tramo : Stream
{
    readonly Stream baseS;
    readonly long inicio, largo;
    long pos;

    public Tramo(Stream s, long inicio, long largo) { baseS = s; this.inicio = inicio; this.largo = largo; }
    public override bool CanRead { get { return true; } }
    public override bool CanSeek { get { return true; } }
    public override bool CanWrite { get { return false; } }
    public override long Length { get { return largo; } }
    public override long Position { get { return pos; } set { pos = value; } }
    public override void Flush() { }
    public override void SetLength(long v) { throw new NotSupportedException(); }
    public override void Write(byte[] b, int o, int c) { throw new NotSupportedException(); }

    public override long Seek(long o, SeekOrigin origen)
    {
        if (origen == SeekOrigin.Begin) pos = o;
        else if (origen == SeekOrigin.Current) pos += o;
        else pos = largo + o;
        return pos;
    }

    public override int Read(byte[] b, int o, int c)
    {
        long resto = largo - pos;
        if (resto <= 0) return 0;
        if (c > resto) c = (int)resto;
        baseS.Seek(inicio + pos, SeekOrigin.Begin);
        int n = baseS.Read(b, o, c);
        pos += n;
        return n;
    }
}

// ---------------------------------------------------------------------------------------------------------- la instalación
class Instalacion
{
    public Action<string, string> Evento;      // PASO / OK / AVISO / FALLO / FIN
    public Action<float> Fraccion;             // avance dentro del paso 1 (0 a 1)
    readonly Paquete paquete;

    public Instalacion(Paquete p) { paquete = p; }

    void E(string tipo, string texto) { if (Evento != null) Evento(tipo, texto); }

    public bool Ejecutar()
    {
        try
        {
            E("PASO", "1");
            if (paquete == null) throw new ApplicationException("Falta el programa dentro del instalador. Descarga el instalador otra vez.");
            Inst.CerrarPrograma();
            Extraer();
            CopiarDesinstalador();
            E("OK", @"AppData\Local\Programs");
            E("PASO", "2");
            Fuentes();
            E("PASO", "3");
            Accesos();
            Registro();
            E("PASO", "4");
            E("OK", File.Exists(Inst.ExeInstalado) ? "Todo listo (no necesita PhotoCraft)" : "Revisa la instalación");
            Thread.Sleep(250);
            E("FIN", VersionApp.V);
            return true;
        }
        catch (Exception ex)
        {
            E("FALLO", Mensaje(ex));
            return false;
        }
    }

    static string Mensaje(Exception ex)
    {
        if (ex is ApplicationException) return ex.Message;
        int hr = Marshal.GetHRForException(ex) & 0xFFFF;
        if (hr == 0x70 || hr == 0x27) return "No hay espacio suficiente en el disco. Libera espacio y vuelve a abrir el instalador.";
        if (ex is UnauthorizedAccessException || hr == 0x20 || hr == 0x21)
            return "Windows no dejó escribir en la carpeta del programa. Cierra Comprobantes y vuelve a abrir el instalador.";
        return ex.Message;
    }

    void Extraer()
    {
        string dir = Inst.CARPETA;
        if (Directory.Exists(dir))
        {
            // borra la versión anterior: la carpeta es solo del programa (el historial y los ajustes están en AppData\Roaming)
            foreach (string d in Directory.GetDirectories(dir)) Inst.BorrarCarpeta(d);
            foreach (string f in Directory.GetFiles(dir)) Inst.BorrarArchivo(f);
        }
        Directory.CreateDirectory(dir);
        string raiz = Path.GetFullPath(dir).TrimEnd('\\') + "\\";
        using (var fs = new FileStream(paquete.Exe, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
        using (var tramo = new Tramo(fs, paquete.Inicio, paquete.Largo))
        using (var zip = new ZipArchive(tramo, ZipArchiveMode.Read))
        {
            long total = 0, hecho = 0;
            foreach (ZipArchiveEntry e in zip.Entries) total += e.Length;
            var buf = new byte[1 << 18];
            foreach (ZipArchiveEntry e in zip.Entries)
            {
                string rel = e.FullName.Replace('/', '\\');
                string destino = Path.GetFullPath(Path.Combine(dir, rel));
                if (!destino.StartsWith(raiz, StringComparison.OrdinalIgnoreCase)) continue;
                if (rel.EndsWith("\\")) { Directory.CreateDirectory(destino); continue; }
                Directory.CreateDirectory(Path.GetDirectoryName(destino));
                using (Stream ent = e.Open())
                using (var sal = new FileStream(destino, FileMode.Create, FileAccess.Write, FileShare.None, 1 << 16))
                {
                    int n;
                    while ((n = ent.Read(buf, 0, buf.Length)) > 0)
                    {
                        sal.Write(buf, 0, n);
                        hecho += n;
                        if (Fraccion != null && total > 0) Fraccion((float)((double)hecho / total));
                    }
                }
            }
        }
        if (!File.Exists(Inst.ExeInstalado))
            throw new ApplicationException("El paquete del instalador está incompleto. Descarga el instalador otra vez.");
    }

    // El desinstalador es este mismo .exe sin el paquete (pesa unos KB)
    void CopiarDesinstalador()
    {
        string destino = Path.Combine(Inst.CARPETA, Inst.DESINSTALADOR);
        using (var ent = new FileStream(paquete.Exe, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
        using (var sal = new FileStream(destino, FileMode.Create, FileAccess.Write))
        {
            var buf = new byte[1 << 16];
            long resto = paquete.Inicio;
            while (resto > 0)
            {
                int n = ent.Read(buf, 0, (int)Math.Min(buf.Length, resto));
                if (n <= 0) break;
                sal.Write(buf, 0, n);
                resto -= n;
            }
        }
    }

    static string NombreFuente(string archivo)
    {
        switch (archivo.ToUpperInvariant())
        {
            case "LEMONMILK-BOLD.OTF": return "LEMON MILK Bold";
            case "GETVOIP GROTESQUE.OTF": return "GetVoIP Grotesque";
            case "MYRIADPRO-BOLD.OTF": return "Myriad Pro Bold";
            case "MYRIADPRO-REGULAR.OTF": return "Myriad Pro Regular";
        }
        return Path.GetFileNameWithoutExtension(archivo);
    }

    static string SinTipo(string nombre)
    {
        int i = nombre.LastIndexOf(" (", StringComparison.Ordinal);
        return (i > 0 ? nombre.Substring(0, i) : nombre).Trim();
    }

    static bool FuenteInstalada(string nombre, string archivo)
    {
        string windir = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
        if (File.Exists(Path.Combine(Path.Combine(windir, "Fonts"), archivo))) return true;
        string stem = Path.GetFileNameWithoutExtension(archivo);
        foreach (RegistryKey raiz in new[] { Registry.LocalMachine, Registry.CurrentUser })
        {
            using (RegistryKey k = raiz.OpenSubKey(CLAVE_FUENTES_LEER))
            {
                if (k == null) continue;
                foreach (string v in k.GetValueNames())
                {
                    string s = SinTipo(v);
                    if (!s.Equals(nombre, StringComparison.OrdinalIgnoreCase) && !s.Equals(stem, StringComparison.OrdinalIgnoreCase)) continue;
                    string ruta = k.GetValue(v) as string;
                    if (string.IsNullOrEmpty(ruta)) continue;
                    if (!Path.IsPathRooted(ruta)) ruta = Path.Combine(Path.Combine(windir, "Fonts"), ruta);
                    if (File.Exists(ruta)) return true;
                }
            }
        }
        return false;
    }

    const string CLAVE_FUENTES_LEER = Inst.CLAVE_FUENTES;

    void Fuentes()
    {
        string origen = Path.Combine(Inst.CARPETA, @"_internal\recursos\fuentes");
        if (!Directory.Exists(origen)) { E("AVISO", "No vienen incluidas: el programa usará fuentes parecidas"); return; }
        string destinoDir = Path.Combine(Inst.LOCAL, @"Microsoft\Windows\Fonts");
        Directory.CreateDirectory(destinoDir);
        int nuevas = 0, total = 0;
        using (RegistryKey k = Registry.CurrentUser.CreateSubKey(Inst.CLAVE_FUENTES))
        {
            foreach (string f in Directory.GetFiles(origen))
            {
                string ext = Path.GetExtension(f).ToLowerInvariant();
                if (ext != ".otf" && ext != ".ttf") continue;
                total++;
                string archivo = Path.GetFileName(f);
                string nombre = NombreFuente(archivo);
                if (FuenteInstalada(nombre, archivo)) continue;
                string destino = Path.Combine(destinoDir, archivo);
                try { File.Copy(f, destino, true); }
                catch (IOException) { if (!File.Exists(destino)) throw; }       // ya estaba y la usa otro programa
                k.SetValue(nombre + (ext == ".otf" ? " (OpenType)" : " (TrueType)"), destino);
                Inst.AddFontResource(destino);
                nuevas++;
            }
        }
        if (nuevas > 0) Inst.PostMessage((IntPtr)0xFFFF, 0x001D, IntPtr.Zero, IntPtr.Zero);   // WM_FONTCHANGE a todos
        if (total == 0) E("AVISO", "No vienen incluidas: el programa usará fuentes parecidas");
        else E("OK", nuevas == 0 ? "Ya estaban instaladas" : (nuevas == 1 ? "1 fuente instalada" : nuevas + " fuentes instaladas"));
    }

    static void CrearAcceso(string lnk, string destino)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(lnk));
        Type tipo = Type.GetTypeFromProgID("WScript.Shell");
        dynamic shell = Activator.CreateInstance(tipo);
        try
        {
            dynamic a = shell.CreateShortcut(lnk);
            a.TargetPath = destino;
            a.WorkingDirectory = Path.GetDirectoryName(destino);
            a.IconLocation = destino + ",0";
            a.Description = "Crea los comprobantes de pago de Cinema Productions";
            a.Save();
            Marshal.FinalReleaseComObject(a);
        }
        finally { Marshal.FinalReleaseComObject(shell); }
    }

    void Accesos()
    {
        CrearAcceso(Inst.AccesoEscritorio, Inst.ExeInstalado);
        CrearAcceso(Inst.AccesoInicio, Inst.ExeInstalado);
        E("OK", "Escritorio y menú Inicio");
    }

    void Registro()
    {
        long bytes = 0;
        foreach (string f in Directory.GetFiles(Inst.CARPETA, "*", SearchOption.AllDirectories)) bytes += new FileInfo(f).Length;
        string des = Path.Combine(Inst.CARPETA, Inst.DESINSTALADOR);
        using (RegistryKey k = Registry.CurrentUser.CreateSubKey(Inst.CLAVE))
        {
            k.SetValue("DisplayName", Inst.NOMBRE);
            k.SetValue("DisplayVersion", VersionApp.V);
            k.SetValue("Publisher", "Cinema Productions");
            k.SetValue("DisplayIcon", Inst.ExeInstalado + ",0");
            k.SetValue("InstallLocation", Inst.CARPETA);
            k.SetValue("UninstallString", "\"" + des + "\" /desinstalar");
            k.SetValue("QuietUninstallString", "\"" + des + "\" /desinstalar /silencioso");
            k.SetValue("InstallDate", DateTime.Now.ToString("yyyyMMdd"));
            k.SetValue("EstimatedSize", (int)(bytes / 1024), RegistryValueKind.DWord);
            k.SetValue("NoModify", 1, RegistryValueKind.DWord);
            k.SetValue("NoRepair", 1, RegistryValueKind.DWord);
        }
        // el instalador anterior (Inno Setup) dejaba su propia entrada: se quita para que no salga dos veces
        try { Registry.CurrentUser.DeleteSubKeyTree(Inst.CLAVE_INNO, false); } catch { }
    }

    // ---- desinstalar (desde «Aplicaciones instaladas»)
    public static int Desinstalar(bool silencioso)
    {
        if (!silencioso)
        {
            DialogResult r = MessageBox.Show(
                "¿Quitar Comprobantes Cinema Productions de esta computadora?\n\n" +
                "Tu historial de clientes y los comprobantes que ya generaste no se borran.",
                "Desinstalar Comprobantes", MessageBoxButtons.YesNo, MessageBoxIcon.Question);
            if (r != DialogResult.Yes) return 1;
        }
        try
        {
            Inst.CerrarPrograma();
            Inst.BorrarArchivo(Inst.AccesoEscritorio);
            Inst.BorrarArchivo(Inst.AccesoInicio);
            try { Registry.CurrentUser.DeleteSubKeyTree(Inst.CLAVE, false); } catch { }
            string yo = Path.GetFullPath(Application.ExecutablePath);
            if (yo.StartsWith(Inst.CARPETA + "\\", StringComparison.OrdinalIgnoreCase))
            {
                // este .exe está dentro de la carpeta: se borra todo lo demás y la carpeta cuando este proceso termine
                foreach (string d in Directory.GetDirectories(Inst.CARPETA)) { try { Inst.BorrarCarpeta(d); } catch { } }
                foreach (string f in Directory.GetFiles(Inst.CARPETA))
                    if (!f.Equals(yo, StringComparison.OrdinalIgnoreCase)) { try { Inst.BorrarArchivo(f); } catch { } }
                var psi = new ProcessStartInfo("cmd.exe", "/c ping 127.0.0.1 -n 3 > nul & rd /s /q \"" + Inst.CARPETA + "\"");
                psi.WorkingDirectory = Path.GetTempPath();
                psi.CreateNoWindow = true;
                psi.UseShellExecute = false;
                psi.WindowStyle = ProcessWindowStyle.Hidden;
                Process.Start(psi);
            }
            else Inst.BorrarCarpeta(Inst.CARPETA);
        }
        catch (Exception ex)
        {
            if (!silencioso) MessageBox.Show("No se pudo desinstalar por completo: " + ex.Message, "Desinstalar Comprobantes",
                                             MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return 2;
        }
        if (!silencioso) MessageBox.Show("Comprobantes Cinema Productions se desinstaló.", "Desinstalar Comprobantes",
                                         MessageBoxButtons.OK, MessageBoxIcon.Information);
        return 0;
    }
}

// ---------------------------------------------------------------------------------------------------------- avance
class Avance
{
    // porcentaje al empezar y al terminar cada paso (0 = preparar) y segundos típicos: dentro de un paso la barra avanza sola
    static readonly float[,] TRAMOS = { { 0, 3 }, { 3, 80 }, { 80, 88 }, { 88, 95 }, { 95, 99 } };
    static readonly double[] DURACION = { 0.5, 9, 1.0, 1.0, 0.6 };

    public int Paso;
    public readonly List<string>[] Detalles = { new List<string>(), new List<string>(), new List<string>(), new List<string>(), new List<string>() };
    public readonly string[] Avisos = { "", "", "", "", "" };
    public string Estado = "instalando";       // instalando | listo | error
    public string Mensaje = "";
    public double Valor;
    public double TPaso, TEstado;
    public volatile float FraccionPaso = -1;
    readonly Queue<string[]> cola = new Queue<string[]>();

    public void Encolar(string tipo, string texto) { lock (cola) cola.Enqueue(new[] { tipo, texto }); }

    public void Drenar(double ahora)
    {
        lock (cola)
        {
            while (cola.Count > 0)
            {
                string[] e = cola.Dequeue();
                Evento(e[0], e[1], ahora);
            }
        }
    }

    void Evento(string tipo, string texto, double ahora)
    {
        if (Estado != "instalando") return;
        switch (tipo)
        {
            case "PASO":
                int n;
                if (int.TryParse(texto, out n) && n > Paso) { Paso = n; TPaso = ahora; if (n != 1) FraccionPaso = -1; }
                break;
            case "OK":
                if (texto.Length > 0) Detalles[Paso].Add(texto);
                break;
            case "AVISO":
                if (texto.Length > 0) Avisos[Paso] = texto;
                break;
            case "FALLO":
                Estado = "error"; Mensaje = texto.Length > 0 ? texto : "Algo salió mal."; TEstado = ahora;
                break;
            case "FIN":
                Estado = "listo"; TEstado = ahora;
                break;
        }
    }

    double Objetivo(double ahora)
    {
        if (Estado == "listo") return 100;
        int i = Math.Min(Math.Max(Paso, 0), 4);
        float a = TRAMOS[i, 0], b = TRAMOS[i, 1];
        double f = 0.9 * (1 - Math.Exp(-(ahora - TPaso) / DURACION[i]));
        float real = FraccionPaso;
        if (i == 1 && real >= 0) f = Math.Max(Math.Min(f, 0.05), real);
        return a + (b - a) * Math.Min(1, f);
    }

    public void Avanzar(double dt, double ahora)
    {
        double obj = Objetivo(ahora);
        Valor += (obj - Valor) * Math.Min(1, dt * (Estado == "listo" ? 5 : 2.4));
    }
}

// ---------------------------------------------------------------------------------------------------------- la ventana
class Ventana : Form
{
    static Color C(uint hex) { return Color.FromArgb(255, (int)((hex >> 16) & 0xff), (int)((hex >> 8) & 0xff), (int)(hex & 0xff)); }
    static Color A(Color c, double a) { return Color.FromArgb((int)Math.Max(0, Math.Min(255, a * 255)), c.R, c.G, c.B); }

    static readonly Color ROJO = C(0xe0262b), CORAL = C(0xff5a5f), NARANJA = C(0xff9a3d);
    static readonly Color TEXTO = C(0xf6f2f2), SUAVE = C(0xbdb3b3), TENUE = C(0x7d7373);
    static readonly Color VERDE = C(0x3ed392), ERROR = C(0xff6b6b), AMBAR = C(0xffc46b);
    static readonly string[] BENEFICIOS = { "Un solo doble clic", "No necesita internet", "No pide permisos de administrador" };
    const float W = 900, H = 520;

    readonly Avance av = new Avance();
    readonly Paquete paquete;
    readonly bool demo, demoError;
    readonly string captura;
    readonly double capturaEn;
    readonly float k;
    readonly Stopwatch reloj = Stopwatch.StartNew();
    readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
    readonly Image icono;
    readonly List<Tuple<double, string, string>> guion = new List<Tuple<double, string, string>>();
    readonly StringFormat tipo = new StringFormat(StringFormat.GenericTypographic);
    double antes, tAbrir = -1, tCerrar = -1;
    bool capturado;
    RectangleF botonCerrar = RectangleF.Empty;
    public int Codigo;

    readonly Font fHeroe, fMarca, fVersion, fBeneficio, fTitulo, fSub, fAccion, fPorc, fPaso, fPasoAct, fDetalle, fPie, fPieB, fBoton;

    public Ventana(Paquete p, bool demo, bool demoError, string captura, double capturaEn)
    {
        paquete = p;
        this.demo = demo || demoError;
        this.demoError = demoError;
        this.captura = captura;
        this.capturaEn = capturaEn;
        tipo.FormatFlags |= StringFormatFlags.MeasureTrailingSpaces | StringFormatFlags.NoWrap;
        using (Graphics g = Graphics.FromHwnd(IntPtr.Zero)) k = Math.Max(1f, g.DpiX / 96f);

        string s = "Segoe UI", sb = "Segoe UI Semibold";
        fHeroe = new Font(s, 28, FontStyle.Bold, GraphicsUnit.Pixel);
        fMarca = new Font(s, 10, FontStyle.Bold, GraphicsUnit.Pixel);
        fVersion = new Font(s, 11, FontStyle.Bold, GraphicsUnit.Pixel);
        fBeneficio = new Font(sb, 13, FontStyle.Regular, GraphicsUnit.Pixel);
        fTitulo = new Font(s, 30, FontStyle.Bold, GraphicsUnit.Pixel);
        fSub = new Font(s, 14, FontStyle.Regular, GraphicsUnit.Pixel);
        fAccion = new Font(sb, 13, FontStyle.Regular, GraphicsUnit.Pixel);
        fPorc = new Font(s, 15, FontStyle.Bold, GraphicsUnit.Pixel);
        fPaso = new Font(s, 14, FontStyle.Regular, GraphicsUnit.Pixel);
        fPasoAct = new Font(sb, 14, FontStyle.Regular, GraphicsUnit.Pixel);
        fDetalle = new Font(s, 12, FontStyle.Regular, GraphicsUnit.Pixel);
        fPie = new Font(s, 13, FontStyle.Regular, GraphicsUnit.Pixel);
        fPieB = new Font(sb, 14, FontStyle.Regular, GraphicsUnit.Pixel);
        fBoton = new Font(s, 14, FontStyle.Bold, GraphicsUnit.Pixel);

        try
        {
            using (Stream st = Assembly.GetExecutingAssembly().GetManifestResourceStream("icono.png"))
                if (st != null) using (Image im = Image.FromStream(st)) icono = new Bitmap(im);
        }
        catch { }
        if (icono == null) icono = Icon.ExtractAssociatedIcon(Application.ExecutablePath).ToBitmap();

        Text = "Instalar Comprobantes";
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.CenterScreen;
        ShowInTaskbar = true;
        KeyPreview = true;
        try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
        BackColor = C(0x0c0909);
        ClientSize = new Size((int)Math.Round(W * k), (int)Math.Round(H * k));
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint | ControlStyles.OptimizedDoubleBuffer, true);
        timer.Interval = 15;
        timer.Tick += Tic;
    }

    protected override CreateParams CreateParams
    {
        get
        {
            CreateParams cp = base.CreateParams;
            cp.ClassStyle |= 0x20000;            // CS_DROPSHADOW: sombra alrededor de la ventana sin marco
            return cp;
        }
    }

    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr h, int atributo, ref int valor, int tam);
    [DllImport("user32.dll")] static extern bool ReleaseCapture();
    [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr h, int msg, IntPtr w, IntPtr l);

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        try { int redondo = 2; DwmSetWindowAttribute(Handle, 33, ref redondo, 4); } catch { }   // esquinas redondeadas (Windows 11)
    }

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        Activate();
        if (demo) EmpezarDemo(); else Empezar();
        antes = reloj.Elapsed.TotalSeconds;
        timer.Start();
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        if (!demo && av.Estado == "instalando" && e.CloseReason == CloseReason.UserClosing) { e.Cancel = true; return; }
        base.OnFormClosing(e);
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        timer.Stop();
        base.OnFormClosed(e);
    }

    void Empezar()
    {
        var inst = new Instalacion(paquete);
        inst.Evento = av.Encolar;
        inst.Fraccion = f => av.FraccionPaso = f;
        var hilo = new Thread(() => { Thread.Sleep(350); inst.Ejecutar(); });
        hilo.IsBackground = true;
        hilo.Start();
    }

    void G(double t, string tipoE, string texto) { guion.Add(Tuple.Create(t, tipoE, texto)); }

    void EmpezarDemo()
    {
        G(0.4, "PASO", "1");
        if (demoError)
        {
            G(2.4, "FALLO", "No hay espacio suficiente en el disco. Libera espacio y vuelve a abrir el instalador.");
            return;
        }
        G(2.6, "OK", @"AppData\Local\Programs");
        G(2.8, "PASO", "2");
        G(3.3, "OK", "4 fuentes instaladas");
        G(3.5, "PASO", "3");
        G(4.0, "OK", "Escritorio y menú Inicio");
        G(4.2, "PASO", "4");
        G(4.6, "OK", "Todo listo (no necesita PhotoCraft)");
        G(5.2, "FIN", VersionApp.V);
    }

    void Tic(object sender, EventArgs e)
    {
        double ahora = reloj.Elapsed.TotalSeconds;
        double dt = Math.Min(0.1, Math.Max(0, ahora - antes));
        antes = ahora;
        while (guion.Count > 0 && guion[0].Item1 <= ahora)
        {
            av.Encolar(guion[0].Item2, guion[0].Item3);
            guion.RemoveAt(0);
        }
        av.Drenar(ahora);
        av.Avanzar(dt, ahora);
        if (av.Estado == "error") Codigo = 1;
        if (av.Estado == "listo" && !demo && tAbrir < 0) tAbrir = ahora + 1.2;
        if (tAbrir > 0 && ahora >= tAbrir && tCerrar < 0)
        {
            Inst.Abrir(Inst.ExeInstalado);
            tCerrar = ahora + 0.8;
        }
        if (captura != null && !capturado && ahora >= capturaEn)
        {
            capturado = true;
            GuardarCaptura(captura, ahora);
            if (demo) { Close(); return; }
        }
        if (tCerrar > 0 && ahora >= tCerrar) { timer.Stop(); Close(); return; }
        Invalidate();
    }

    void GuardarCaptura(string ruta, double t)
    {
        const float esc = 2f;
        try
        {
            using (var bmp = new Bitmap((int)(W * esc), (int)(H * esc), PixelFormat.Format32bppArgb))
            using (Graphics g = Graphics.FromImage(bmp))
            {
                g.Clear(Color.Transparent);
                g.SmoothingMode = SmoothingMode.AntiAlias;
                using (GraphicsPath p = Redondeado(0, 0, W * esc, H * esc, 10 * esc)) g.SetClip(p);
                Pintar(g, esc, t);
                Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(ruta)));
                bmp.Save(ruta, ImageFormat.Png);
            }
        }
        catch { }
    }

    // ---- ratón y teclado
    protected override void OnMouseDown(MouseEventArgs e)
    {
        base.OnMouseDown(e);
        if (e.Button != MouseButtons.Left) return;
        var pt = new PointF(e.X / k, e.Y / k);
        if (!botonCerrar.IsEmpty && botonCerrar.Contains(pt)) { Close(); return; }
        ReleaseCapture();
        SendMessage(Handle, 0xA1, (IntPtr)2, IntPtr.Zero);       // arrastrar la ventana desde cualquier parte
    }

    protected override void OnMouseMove(MouseEventArgs e)
    {
        base.OnMouseMove(e);
        var pt = new PointF(e.X / k, e.Y / k);
        Cursor = (!botonCerrar.IsEmpty && botonCerrar.Contains(pt)) ? Cursors.Hand : Cursors.Default;
    }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        base.OnKeyDown(e);
        if (e.KeyCode == Keys.Escape && (demo || av.Estado != "instalando")) Close();
    }

    // ---- dibujo
    protected override void OnPaint(PaintEventArgs e) { Pintar(e.Graphics, k, reloj.Elapsed.TotalSeconds); }

    Color ColorEstado { get { return av.Estado == "listo" ? VERDE : (av.Estado == "error" ? ERROR : ROJO); } }

    void Pintar(Graphics g, float esc, double t)
    {
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
        g.InterpolationMode = InterpolationMode.HighQualityBicubic;
        g.PixelOffsetMode = PixelOffsetMode.HighQuality;
        g.CompositingQuality = CompositingQuality.HighQuality;
        g.ScaleTransform(esc, esc);
        using (var b = new LinearGradientBrush(new RectangleF(0, 0, W, H), C(0x1b1515), C(0x0c0909), 35f)) g.FillRectangle(b, -1, -1, W + 2, H + 2);
        Heroe(g, t);
        Columna(g, t);
        Color borde = av.Estado == "listo" ? A(VERDE, 0.6) : (av.Estado == "error" ? A(ERROR, 0.6) : C(0x3d2a2a));
        using (var pen = new Pen(borde, 1.2f))
        using (GraphicsPath p = Redondeado(0.6f, 0.6f, W - 1.2f, H - 1.2f, 9)) g.DrawPath(pen, p);
    }

    static GraphicsPath Redondeado(float x, float y, float w, float h, float r)
    {
        var p = new GraphicsPath();
        float d = r * 2;
        p.AddArc(x, y, d, d, 180, 90);
        p.AddArc(x + w - d, y, d, d, 270, 90);
        p.AddArc(x + w - d, y + h - d, d, d, 0, 90);
        p.AddArc(x, y + h - d, d, d, 90, 90);
        p.CloseFigure();
        return p;
    }

    static void Capsula(Graphics g, Brush b, float x, float y, float w, float h)
    {
        if (w < h) w = h;
        using (GraphicsPath p = Redondeado(x, y, w, h, h / 2)) g.FillPath(b, p);
    }

    static void Brillo(Graphics g, Color c, float cx, float cy, float r, double alfa)
    {
        if (r <= 0 || alfa <= 0) return;
        using (var p = new GraphicsPath())
        {
            p.AddEllipse(cx - r, cy - r, 2 * r, 2 * r);
            using (var b = new PathGradientBrush(p))
            {
                b.CenterPoint = new PointF(cx, cy);
                b.CenterColor = A(c, alfa);
                b.SurroundColors = new[] { A(c, 0) };
                var mezcla = new Blend(3);
                mezcla.Factors = new[] { 0f, 0.55f, 1f };
                mezcla.Positions = new[] { 0f, 0.5f, 1f };
                b.Blend = mezcla;
                g.FillPath(b, p);
            }
        }
    }

    static void Palomita(Graphics g, float cx, float cy, float s, Color c, float grosor)
    {
        using (var pen = new Pen(c, grosor))
        {
            pen.StartCap = LineCap.Round; pen.EndCap = LineCap.Round; pen.LineJoin = LineJoin.Round;
            g.DrawLines(pen, new[] { new PointF(cx - 0.42f * s, cy + 0.02f * s), new PointF(cx - 0.12f * s, cy + 0.3f * s),
                                     new PointF(cx + 0.42f * s, cy - 0.28f * s) });
        }
    }

    float Ancho(Graphics g, string s, Font f) { return g.MeasureString(s, f, PointF.Empty, tipo).Width; }

    void Texto(Graphics g, string s, Font f, Color c, float x, float y)
    {
        using (var b = new SolidBrush(c)) g.DrawString(s, f, b, x, y, tipo);
    }

    void Centrado(Graphics g, string s, Font f, Color c, float cx, float y, float espacio)
    {
        if (espacio <= 0) { Texto(g, s, f, c, cx - Ancho(g, s, f) / 2, y); return; }
        float total = 0;
        foreach (char ch in s) total += Ancho(g, ch.ToString(), f) + espacio;
        total -= espacio;
        float x = cx - total / 2;
        using (var b = new SolidBrush(c))
            foreach (char ch in s)
            {
                string t = ch.ToString();
                g.DrawString(t, f, b, x, y, tipo);
                x += Ancho(g, t, f) + espacio;
            }
    }

    void Heroe(Graphics g, double t)
    {
        var r = new RectangleF(0, 0, 330, H);
        using (var b = new LinearGradientBrush(r, C(0x4c0f13), C(0x120c0c), 55f))
        {
            var cb = new ColorBlend(3);
            cb.Colors = new[] { C(0x4c0f13), C(0x25110f), C(0x120c0c) };
            cb.Positions = new[] { 0f, 0.5f, 1f };
            b.InterpolationColors = cb;
            g.FillRectangle(b, -1, -1, 331, H + 2);
        }
        GraphicsState estado = g.Save();
        g.SetClip(r);
        Luz(g, ROJO, 0.25, 0.20, 264, 0.21, 0, t);
        Luz(g, NARANJA, 0.85, 0.80, 280, 0.17, 1, t);
        Luz(g, CORAL, 0.55, 0.50, 182, 0.13, 2, t);
        g.Restore(estado);

        Emblema(g, 165, 160, t);
        Centrado(g, "Comprobantes", fHeroe, TEXTO, 165, 252, 0);
        Centrado(g, "CINEMA PRODUCTIONS", fMarca, A(TEXTO, 0.6), 165, 295, 2.5f);
        Centrado(g, "INSTALADOR  ·  v" + VersionApp.V, fVersion, A(CORAL, 0.95), 165, 317, 3f);

        float y = 396;
        foreach (string ben in BENEFICIOS)
        {
            using (var b = new SolidBrush(A(CORAL, 0.2))) g.FillEllipse(b, 40, y, 20, 20);
            Palomita(g, 50, y + 10, 9, CORAL, 2f);
            Texto(g, ben, fBeneficio, A(TEXTO, 0.88), 70, y + 1);
            y += 34;
        }

        var linea = new RectangleF(329.5f, 24, 1, H - 48);
        using (var b = new LinearGradientBrush(linea, A(CORAL, 0), A(CORAL, 0), 90f))
        {
            var cb = new ColorBlend(3);
            cb.Colors = new[] { A(CORAL, 0), A(CORAL, 0.35), A(CORAL, 0) };
            cb.Positions = new[] { 0f, 0.5f, 1f };
            b.InterpolationColors = cb;
            g.FillRectangle(b, linea);
        }
    }

    static void Luz(Graphics g, Color c, double fx, double fy, float r, double vel, double i, double t)
    {
        float x = (float)(330 * (fx + 0.12 * Math.Sin(t * vel * 2 + i)));
        float y = (float)(H * (fy + 0.08 * Math.Cos(t * vel * 1.6 + i * 2)));
        Brillo(g, c, x, y, r, 0.17);
    }

    static Color Mezclar(Color a, Color b, float u)
    {
        return Color.FromArgb((int)(a.A + (b.A - a.A) * u), (int)(a.R + (b.R - a.R) * u), (int)(a.G + (b.G - a.G) * u),
                              (int)(a.B + (b.B - a.B) * u));
    }

    static Color EnDegradado(Color[] cs, float[] ps, float f)
    {
        for (int i = 1; i < ps.Length; i++)
            if (f <= ps[i]) return Mezclar(cs[i - 1], cs[i], (f - ps[i - 1]) / Math.Max(0.0001f, ps[i] - ps[i - 1]));
        return cs[cs.Length - 1];
    }

    void Emblema(Graphics g, float cx, float cy, double t)
    {
        bool inst = av.Estado == "instalando";
        double ang = (t * (inst ? 300 : 60)) % 360;
        double kk = t - av.TEstado;
        double pulso = inst ? 0.75 + 0.25 * Math.Sin(t * 2.2) : 1 + 0.8 * Math.Exp(-kk * 2.2);
        Color ce = ColorEstado;

        Brillo(g, ce, cx, cy, 138, Math.Min(1, 0.34 * pulso));
        using (var b = new SolidBrush(Color.FromArgb(240, 0x14, 0x0c, 0x0c))) g.FillEllipse(b, cx - 60, cy - 60, 120, 120);
        using (var pen = new Pen(Color.FromArgb(26, 255, 255, 255), 1)) g.DrawEllipse(pen, cx - 60, cy - 60, 120, 120);

        Color[] cs; float[] ps;
        if (inst)
        {
            cs = new[] { CORAL, A(ROJO, 0.7), A(NARANJA, 0), A(NARANJA, 0), A(NARANJA, 0.9) };
            ps = new[] { 0f, 0.18f, 0.38f, 0.7f, 1f };
        }
        else
        {
            cs = new[] { ce, A(ce, 0.55), ce };
            ps = new[] { 0f, 0.5f, 1f };
        }
        const int N = 90;
        for (int s = 0; s < N; s++)
        {
            float f = s / (float)N;
            Color c = EnDegradado(cs, ps, f);
            if (c.A < 3) continue;
            using (var pen = new Pen(c, 4f)) g.DrawArc(pen, cx - 69, cy - 69, 138, 138, (float)(ang + f * 360), 360f / N + 0.9f);
        }
        Color[] puntos = { NARANJA, CORAL, ROJO };
        for (int i = 0; i < 3; i++)
        {
            double a = (-ang * 0.55 + i * 120) * Math.PI / 180;
            using (var b = new SolidBrush(A(inst ? puntos[i] : ce, 0.8)))
                g.FillEllipse(b, cx + (float)(Math.Cos(a) * 84) - 3, cy + (float)(Math.Sin(a) * 84) - 3, 6, 6);
        }
        float dy = (float)(Math.Sin(t * 1.7) * 2.5);
        if (icono != null) g.DrawImage(icono, cx - 48, cy - 48 + dy, 96, 96);
        if (!inst)
        {
            float bx = cx + 41, by = cy + 41;
            using (var b = new SolidBrush(ce)) g.FillEllipse(b, bx - 17, by - 17, 34, 34);
            using (var pen = new Pen(C(0x140c0c), 3)) g.DrawEllipse(pen, bx - 17, by - 17, 34, 34);
            if (av.Estado == "listo") Palomita(g, bx, by, 15, Color.White, 3f);
            else
                using (var f = new Font("Segoe UI", 20, FontStyle.Bold, GraphicsUnit.Pixel))
                    Centrado(g, "!", f, Color.White, bx, by - 14, 0);
        }
    }

    string Titulo
    {
        get { return av.Estado == "listo" ? "¡Comprobantes está listo!" : (av.Estado == "error" ? "No se pudo instalar" : "Instalando Comprobantes"); }
    }

    string Subtitulo
    {
        get
        {
            if (av.Estado == "listo") return "Se instaló la versión " + VersionApp.V + ". Lo encuentras en el escritorio y en el menú Inicio.";
            if (av.Estado == "error") return av.Mensaje;
            return "Versión " + VersionApp.V + " para Windows";
        }
    }

    string Accion
    {
        get
        {
            if (av.Estado == "listo") return "Instalación completa";
            if (av.Estado == "error") return "Se detuvo en: " + Inst.PASOS[Math.Max(0, av.Paso - 1)];
            if (av.Paso == 0) return "Preparando el instalador…";
            return "Paso " + av.Paso + " de " + Inst.PASOS.Length + " · " + Inst.PASOS[av.Paso - 1];
        }
    }

    void Columna(Graphics g, double t)
    {
        const float x = 376, w = 480;
        Texto(g, Titulo, fTitulo, TEXTO, x - 1, 40);
        using (var b = new SolidBrush(av.Estado == "error" ? ERROR : SUAVE))
        using (var sf = new StringFormat(StringFormat.GenericTypographic))
        {
            sf.Trimming = StringTrimming.EllipsisWord;
            g.DrawString(Subtitulo, fSub, b, new RectangleF(x, 90, w, 42), sf);
        }
        using (var b = new SolidBrush(SUAVE))
        using (var sf = new StringFormat(tipo))
        {
            sf.Trimming = StringTrimming.EllipsisCharacter;
            g.DrawString(Accion, fAccion, b, new RectangleF(x, 147, w - 70, 20), sf);
        }
        string porc = (int)Math.Round(av.Valor) + " %";
        Texto(g, porc, fPorc, TEXTO, x + w - Ancho(g, porc, fPorc), 145);
        Barra(g, x, 174, w);
        for (int i = 1; i <= Inst.PASOS.Length; i++) Fila(g, i, x, 202 + (i - 1) * 40, w, t);
        Pie(g, x, w);
    }

    void Barra(Graphics g, float x, float y, float w)
    {
        float wv = Math.Max(10, w * (float)Math.Min(100, av.Valor) / 100);
        using (var b = new SolidBrush(Color.FromArgb(18, 255, 255, 255))) Capsula(g, b, x, y, w, 10);
        Color[] cs = av.Estado == "listo" ? new[] { C(0x23a86e), C(0x5fd6a0) }
                   : (av.Estado == "error" ? new[] { C(0xc2444a), ERROR } : new[] { CORAL, ROJO, NARANJA });
        using (var b = new LinearGradientBrush(new RectangleF(x - 1, y, wv + 2, 10), cs[0], cs[cs.Length - 1], 0f))
        {
            if (cs.Length == 3)
            {
                var cb = new ColorBlend(3);
                cb.Colors = cs;
                cb.Positions = new[] { 0f, 0.5f, 1f };
                b.InterpolationColors = cb;
            }
            Capsula(g, b, x, y, wv, 10);
        }
        if (av.Estado == "instalando") Brillo(g, NARANJA, x + wv - 3, y + 5, 16, 0.55);
    }

    void Fila(Graphics g, int i, float x, float y, float w, double t)
    {
        bool listo = av.Estado == "listo";
        bool hecho = listo || i < av.Paso;
        bool actual = !listo && i == av.Paso;
        string detalle = "";
        Color cdet = TENUE;
        if (av.Avisos[i].Length > 0) { detalle = av.Avisos[i]; cdet = A(AMBAR, 0.92); }
        else if (hecho && av.Detalles[i].Count > 0)
        {
            List<string> d = av.Detalles[i];
            detalle = d.Count > 1 ? d[d.Count - 2] + " · " + d[d.Count - 1] : d[0];
        }
        string nombre = i == 1 ? "Programa Comprobantes " + VersionApp.V : Inst.PASOS[i - 1];
        float cx = x + 11, cy = y + 19;

        if (hecho && av.Avisos[i].Length == 0)
        {
            using (var b = new LinearGradientBrush(new RectangleF(cx - 11, cy - 11, 22, 22), CORAL, ROJO, 45f)) g.FillEllipse(b, cx - 11, cy - 11, 22, 22);
            Palomita(g, cx, cy, 10, Color.White, 2.2f);
        }
        else if (hecho || (actual && av.Estado == "error"))
        {
            bool aviso = hecho;
            using (var b = new SolidBrush(aviso ? AMBAR : ERROR)) g.FillEllipse(b, cx - 11, cy - 11, 22, 22);
            using (var f = new Font("Segoe UI", 14, FontStyle.Bold, GraphicsUnit.Pixel))
                Centrado(g, "!", f, aviso ? C(0x2a1d08) : Color.White, cx, cy - 10, 0);
        }
        else if (actual)
        {
            using (var pen = new Pen(A(CORAL, 0.22), 2.4f)) g.DrawEllipse(pen, cx - 9.5f, cy - 9.5f, 19, 19);
            using (var pen = new Pen(CORAL, 2.6f))
            {
                pen.StartCap = LineCap.Round; pen.EndCap = LineCap.Round;
                g.DrawArc(pen, cx - 9.5f, cy - 9.5f, 19, 19, (float)((t * 420) % 360), 100);
            }
        }
        else
        {
            using (var pen = new Pen(A(TENUE, 0.7), 1.6f)) g.DrawEllipse(pen, cx - 9, cy - 9, 18, 18);
        }

        Font fn = actual ? fPasoAct : fPaso;
        Texto(g, nombre, fn, hecho || actual ? TEXTO : TENUE, x + 34, y + 10);
        if (detalle.Length > 0)
        {
            float x0 = x + 34 + Ancho(g, nombre, fn) + 14;
            using (var b = new SolidBrush(cdet))
            using (var sf = new StringFormat(tipo))
            {
                sf.Alignment = StringAlignment.Far;
                sf.Trimming = StringTrimming.EllipsisCharacter;
                g.DrawString(detalle, fDetalle, b, new RectangleF(x0, y + 12, x + w - x0, 18), sf);
            }
        }
    }

    void Pie(Graphics g, float x, float w)
    {
        botonCerrar = RectangleF.Empty;
        if (av.Estado == "error")
        {
            float bw = Ancho(g, "Cerrar", fBoton) + 52;
            var r = new RectangleF(x, 444, bw, 44);
            using (var b = new LinearGradientBrush(r, CORAL, NARANJA, 0f))
            {
                var cb = new ColorBlend(3);
                cb.Colors = new[] { CORAL, ROJO, NARANJA };
                cb.Positions = new[] { 0f, 0.5f, 1f };
                b.InterpolationColors = cb;
                Capsula(g, b, r.X, r.Y, r.Width, r.Height);
            }
            Centrado(g, "Cerrar", fBoton, Color.White, r.X + bw / 2, r.Y + 12, 0);
            botonCerrar = r;
            Texto(g, "Ábrelo otra vez; si se repite, avísanos.", fDetalle, TENUE, x + bw + 18, 459);
        }
        else if (av.Estado == "listo")
            Texto(g, demo ? "Listo (demostración)" : "Abriendo Comprobantes…", fPieB, VERDE, x, 456);
        else
            Texto(g, "Puedes seguir usando tu computadora. Al terminar, Comprobantes se abre solo.", fPie, TENUE, x, 457);
    }
}

// ---------------------------------------------------------------------------------------------------------- inicio
static class Programa
{
    [STAThread]
    static int Main(string[] args)
    {
        bool desinstalar = false, silencioso = false, reparar = false, demo = false, demoError = false;
        string captura = null;
        double en = 2.5;
        foreach (string a0 in args)
        {
            string a = a0.Trim();
            string al = a.ToLowerInvariant();
            if (al == "/desinstalar") desinstalar = true;
            else if (al == "/silencioso") silencioso = true;
            else if (al == "/reparar") reparar = true;
            else if (al == "/demo") demo = true;
            else if (al == "/demo-error") demoError = true;
            else if (al.StartsWith("/captura=")) captura = a.Substring(9).Trim('"');
            else if (al.StartsWith("/en="))
                double.TryParse(a.Substring(4), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out en);
        }
        try { Inst.SetProcessDPIAware(); } catch { }

        if (desinstalar) return Instalacion.Desinstalar(silencioso);

        bool nuevo;
        using (var unico = new Mutex(true, "ComprobantesCinemaProductions.Instalador", out nuevo))
        {
            if (!nuevo && !demo && !demoError) return 0;           // ya hay un instalador abierto
            Paquete paquete = Paquete.Abrir(Application.ExecutablePath);
            bool simulado = demo || demoError;

            if (!simulado && !reparar)
            {
                string inst = Inst.VersionInstalada();
                if (inst != null && File.Exists(Inst.ExeInstalado) && Inst.NumeroVersion(inst) >= Inst.NumeroVersion(VersionApp.V))
                {
                    if (!silencioso) Inst.Abrir(Inst.ExeInstalado);          // ya está instalado: solo se abre
                    return 0;
                }
            }
            if (silencioso && !simulado)
            {
                var ins = new Instalacion(paquete);
                string error = null;
                ins.Evento = (t, s) => { if (t == "FALLO") error = s; };
                bool ok = ins.Ejecutar();
                if (!ok) Console.Error.WriteLine(error);
                return ok ? 0 : 1;
            }
            if (paquete == null && !simulado)
            {
                MessageBox.Show("Este instalador está incompleto (le falta el programa). Descárgalo otra vez.", "Instalar Comprobantes",
                                MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            var v = new Ventana(paquete, demo, demoError, captura, en);
            Application.Run(v);
            return v.Codigo;
        }
    }
}
