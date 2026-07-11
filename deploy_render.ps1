$headers = @{
    "Authorization" = "Bearer rnd_M38zWxuG4tBOlVSyg4Mpgi9KTJ06"
    "Content-Type" = "application/json"
}

$body = @{
    type = "web_service"
    name = "remateup-backend"
    owner_id = "tea-d99c10cs728c73d1p96g"
    repo = "https://github.com/mikepty/remateup"
    branch = "master"
    serviceDetails = @{
        env = "python"
        buildCommand = "cd backend && pip install -r requirements.txt"
        startCommand = "cd backend && uvicorn app.main:app --host 0.0.0.0 --port `$PORT"
    }
} | ConvertTo-Json -Depth 10

Write-Host "Creating Render service..."
Write-Host "Body: $body"

try {
    $response = Invoke-RestMethod -Uri "https://api.render.com/v1/services" -Method Post -Headers $headers -Body $body
    Write-Host "Success!"
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "Error: $($_.Exception.Message)"
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $reader.ReadToEnd()
    }
}
