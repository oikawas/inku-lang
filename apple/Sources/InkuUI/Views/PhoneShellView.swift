import SwiftUI

/// The iPhone tab bar's tags. The camera's is a start, never a selection (`ContentView.phoneTab`).
enum PhoneShellTab {
    static let creation = 0, library = 1, settings = 2, camera = 3
}

/// The iPhone shell (ios-app step 7, the author's choice 2026-11-09 "案 1 タブで分ける"): 制作, カメラ, ライブラリ and
/// 設定 in the tab bar. The tabs show the same views as the Mac's workspace, library and settings; `ContentView` owns their
/// state, so a tab is the Mac's "library open" or "settings open".
@MainActor
struct PhoneShellView<Creation: View, Library: View, Settings: View>: View {
    @Bindable var model: AppModel
    @Binding var tab: Int
    /// The run's status line (a drawing's stage or the batch's), shown above the tabs while another tab is chosen.
    let runStatus: String
    @ViewBuilder let creation: () -> Creation
    @ViewBuilder let library: () -> Library
    @ViewBuilder let settings: () -> Settings

    private var display: DisplaySettings { model.display }

    var body: some View {
        TabView(selection: $tab) {
            NavigationStack { creation() }
                .tabItem { Label(display.localized("制作"), systemImage: "paintbrush") }
                .tag(0)
            // The camera, second as on Android (author 2026-11-13), is a button rather than a page: `ContentView`'s
            // selection takes this tag as the camera's start and keeps the tab that was chosen.
            Color.clear
                .tabItem { Label(display.localized("カメラ"), systemImage: "camera") }
                .tag(PhoneShellTab.camera)
            library()
                .tabItem { Label(display.webCopy("historyLibraryTitle", "ライブラリ"), systemImage: "square.grid.3x3") }
                .tag(1)
            settings()
                .tabItem { Label(display.webCopy("settingsTitle", "設定"), systemImage: "gearshape") }
                .tag(2)
        }
        .inkuTabRunAccessory(visible: model.hasActiveRun && tab != 0) { runRow }
    }

    /// Back to 制作 on a tap; the stop button stops every run, as each stop button would.
    private var runRow: some View {
        HStack(spacing: 10) {
            ProgressView().controlSize(.small)
            Text(runStatus.isEmpty ? display.localized("描画中") : display.message(runStatus))
                .inkuFont(12).lineLimit(1)
                .frame(maxWidth: .infinity, alignment: .leading)
            Button(role: .destructive) { Task { await model.stopEveryRun() } } label: {
                Label(display.localized("停止"), systemImage: "stop.fill").inkuFont(12)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
        .padding(.horizontal, 14)
        .contentShape(Rectangle())
        .onTapGesture { tab = 0 }
    }
}
