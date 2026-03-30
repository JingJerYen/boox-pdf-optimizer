/**
 * Watches a Google Drive folder for new BOOX PDFs and sends them
 * to the Cloud Function for optimization.
 *
 * Setup:
 *   1. Set script properties (File > Project settings > Script properties):
 *      - FOLDER_ID         : the Drive folder ID to watch
 *      - CLOUD_FUNCTION_URL: the Cloud Function HTTP endpoint
 *      - AUTH_TOKEN        : the shared secret from deploy.sh
 *
 *   2. Add a time-driven trigger:
 *      Triggers > Add trigger > watchFolder > Time-driven > Every 1 minute
 */

function watchFolder() {
  var props = PropertiesService.getScriptProperties();
  var folderId = props.getProperty("FOLDER_ID");
  var url = props.getProperty("CLOUD_FUNCTION_URL");
  var token = props.getProperty("AUTH_TOKEN");

  if (!folderId || !url || !token) {
    Logger.log("Missing script properties. Set FOLDER_ID, CLOUD_FUNCTION_URL, AUTH_TOKEN.");
    return;
  }

  var folder = DriveApp.getFolderById(folderId);

  // Build set of all existing file names to skip already-optimized files
  var existingNames = {};
  var allFiles = folder.getFiles();
  while (allFiles.hasNext()) {
    existingNames[allFiles.next().getName()] = true;
  }

  // Find PDFs that need optimization
  var files = folder.getFilesByType(MimeType.PDF);
  while (files.hasNext()) {
    var file = files.next();
    var name = file.getName();

    // Skip files that are already optimized
    if (name.indexOf("_optimized.pdf") !== -1) continue;

    // Skip if optimized version already exists
    var optimizedName = name.replace(/\.pdf$/i, "_optimized.pdf");
    if (existingNames[optimizedName]) continue;

    // Get OAuth token for this user — Cloud Function uses it to upload back to Drive
    var uploadToken = ScriptApp.getOAuthToken();

    Logger.log("Optimizing: " + name);
    try {
      var response = UrlFetchApp.fetch(url, {
        method: "post",
        contentType: "application/json",
        headers: { "X-Auth-Token": token },
        payload: JSON.stringify({
          file_id: file.getId(),
          file_name: name,
          folder_id: folderId,
          upload_token: uploadToken
        }),
        muteHttpExceptions: true
      });

      var code = response.getResponseCode();
      if (code !== 200) {
        Logger.log("Error " + code + ": " + response.getContentText());
        return;
      }

      var result = JSON.parse(response.getContentText());
      Logger.log("Done: " + name + " → " + result.out_size_mb + " MB (" + result.ratio + "x smaller)");

    } catch (e) {
      Logger.log("Failed: " + e.message);
    }

    // Process only one file per invocation to stay within time limits
    return;
  }

  Logger.log("No new PDFs to process.");
}
