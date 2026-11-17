-- Instalador de un clic de Comprobantes Cinema Productions (Mac)
-- Copia el programa a Aplicaciones, lo agrega al Dock, lo abre, expulsa el disco y se cierra.
-- El programa va dentro de este instalador: Contents/Resources/Comprobantes Cinema.app

on run
	set nombreApp to "Comprobantes Cinema.app"
	set yo to POSIX path of (path to me)
	set origen to yo & "Contents/Resources/" & nombreApp

	-- Aplicaciones de la Mac; si el usuario no tiene permiso, su carpeta Aplicaciones personal
	set carpeta to "/Applications"
	try
		do shell script "test -w /Applications"
	on error
		set carpeta to (POSIX path of (path to home folder)) & "Applications"
		do shell script "mkdir -p " & quoted form of carpeta
	end try
	set destino to carpeta & "/" & nombreApp

	set progress total steps to 3
	set progress description to "Instalando Comprobantes Cinema…"
	set progress additional description to "Copiando el programa a Aplicaciones"
	set progress completed steps to 0
	try
		-- Si hay una versión abierta se cierra; se reemplaza la anterior
		do shell script "pkill -f " & quoted form of (nombreApp & "/Contents/MacOS/") & " >/dev/null 2>&1; sleep 1; rm -rf " & quoted form of destino & " && ditto --noqtn " & quoted form of origen & " " & quoted form of destino
	on error mensaje
		display dialog "No se pudo instalar Comprobantes Cinema:" & return & mensaje buttons {"Cerrar"} default button 1 with icon stop
		return
	end try

	set progress completed steps to 1
	set progress additional description to "Agregando al Dock"
	try
		do shell script "if ! defaults read com.apple.dock persistent-apps 2>/dev/null | grep -qi 'comprobantes'; then defaults write com.apple.dock persistent-apps -array-add '<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>" & destino & "</string><key>_CFURLStringType</key><integer>0</integer></dict></dict></dict>'; killall Dock; fi"
	end try

	set progress completed steps to 2
	set progress additional description to "Abriendo el programa"
	do shell script "open " & quoted form of destino
	set progress completed steps to 3
	display notification "Ya está en Aplicaciones y en el Dock." with title "Comprobantes Cinema instalado"

	-- Si se abrió desde el .dmg, se expulsa el disco al terminar
	if yo starts with "/Volumes/" then
		set volumen to do shell script "echo " & quoted form of yo & " | cut -d/ -f1-3"
		do shell script "(sleep 3; hdiutil detach " & quoted form of volumen & " -quiet || hdiutil detach " & quoted form of volumen & " -force -quiet) >/dev/null 2>&1 &"
	end if
end run
