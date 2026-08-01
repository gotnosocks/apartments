async function configureSidePanel() {
  if (chrome.sidePanel?.setPanelBehavior) {
    await chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true});
  }
}

chrome.runtime.onInstalled.addListener(() => configureSidePanel().catch(console.error));
chrome.runtime.onStartup.addListener(() => configureSidePanel().catch(console.error));
configureSidePanel().catch(console.error);
