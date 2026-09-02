import QtQuick
import Quickshell
import qs.Ui

BarWidget {
  id: root
  moduleName: "io.github.djspatule.tts-clip"

  function speak() {
    Quickshell.execDetached(["tts-clip"])
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "\uD83D\uDD0A"
    tooltipText: "Speak clipboard"
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.LeftButton) root.speak()
    }
  }
}
