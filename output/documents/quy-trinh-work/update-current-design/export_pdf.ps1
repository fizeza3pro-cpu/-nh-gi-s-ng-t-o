param([Parameter(Mandatory=$true)][string]$InputFile, [Parameter(Mandatory=$true)][string]$OutputFile)
$ErrorActionPreference = 'Stop'
$wordApp = $null
$wordDocument = $null
$noSave = 0
try {
    $wordApp = New-Object -ComObject Word.Application
    $wordApp.Visible = $false
    $wordApp.DisplayAlerts = 0
    $wordApp.AutomationSecurity = 3
    $wordDocument = $wordApp.Documents.Open([IO.Path]::GetFullPath($InputFile), $false, $true, $false)
    $wordDocument.Repaginate()
    $wordDocument.ExportAsFixedFormat([IO.Path]::GetFullPath($OutputFile), 17)
    Write-Output ('PAGES=' + $wordDocument.ComputeStatistics(2))
} finally {
    if ($null -ne $wordDocument) {
        $wordDocument.Close([ref]$noSave)
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($wordDocument)
    }
    if ($null -ne $wordApp) {
        if ($wordApp.Documents.Count -eq 0) { $wordApp.Quit([ref]$noSave) }
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($wordApp)
    }
}
