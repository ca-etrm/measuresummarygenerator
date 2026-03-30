import logging
import math
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    KeepTogether,
    Table,
    Paragraph,
    Flowable
)

from src import assets, __version__, __trm_version_date__, __trm_title__
from src.summarygen import utils
from src.summarygen.styles import (
    INNER_WIDTH,
    INNER_HEIGHT,
    TSTYLES,
    PSTYLES,
    COLORS
)

logger = logging.getLogger(__name__)

class VersionContainer(Flowable):
    def __init__(self, ipadx: float = 9.0, ipady: float = 4.0) -> None:
        self._ipadx = ipadx
        self._ipady = ipady
        self._style = style = PSTYLES["VersionContainer"].bold
        self._text = f"VERSION {__version__}"
        text_width = stringWidth(self._text, style.font_name, style.font_size)
        self._width = text_width + ipadx * 2
        self._height = style.leading + ipady * 2

    def wrap(self, *args) -> tuple[float, float]:
        return (self._width, self._height)

    def draw(self) -> None:
        canvas = self.canv
        if not isinstance(canvas, Canvas):
            return

        canvas.saveState()
        try:
            canvas.setFillColor(COLORS["LightBlack"])
            canvas.roundRect(0, 0, self._width, self._height, 4, stroke=0, fill=1)
            canvas.restoreState()

            canvas.saveState()
            text_obj = canvas.beginText(self._ipadx, self._ipady * 1.75)
            text_obj.setFont(self._style.font_name, self._style.font_size, self._style.leading)
            text_obj.setFillColor(self._style.text_color)
            text_obj.textOut(self._text)
            canvas.drawText(text_obj)
        finally:
            canvas.restoreState()


class CoverPage(KeepTogether):                                         #Class inherits KeepTogether of ReportLab which inherits flowable
    def __init__(self) -> None:
        logger.info("Initiate src.summarygen.flowable.coverpage.CoverPage")
        # Build top content container (the eTRM logo and caption at top right corner)
        img_path = assets.get_path("images/etrm.png")                  #Image:
        img_obj = utils.get_image(img_path, max_height=120)
        caption_style = PSTYLES["CoverCaption"].bold
        max_width = 0

        for text in ["California", "Statewide", "Deemed", "Measures"]: #Text: Get the max width of the text
            width = stringWidth(text, caption_style.font_name, caption_style.font_size)
            max_width = max(max_width, width)
        title_obj = Table(                                             #Text: Draw a 4x1 table for the caption text
            [
                [Paragraph("California", style=caption_style)],
                [Paragraph("Statewide", style=caption_style)],
                [Paragraph("Deemed", style=caption_style)],
                [Paragraph("Measures", style=caption_style)]
            ],
            hAlign="LEFT",
            style=TSTYLES["CoverCaption"]
        )
        
        spacer = 10
        
        top_table = Table(                                              #Together: Draw a 1x4 table to put logo and caption together
            [["", img_obj, "", title_obj]],
            colWidths=[
                INNER_WIDTH - max_width - img_obj.drawWidth - spacer,
                img_obj.drawWidth,
                spacer,
                max_width
            ],
            style=TSTYLES["CoverTopContent"]
        )
        data = [[top_table]]                                            #CoverSheetTotal: Add top_table to a list of tables
        top_height = max(img_obj.drawHeight, caption_style.leading * 4)

        # Build middle content container (cover page title)
        # title_para = Paragraph(                                         #Draw the paragraph flowable
        #     "Technical Reference Manual for California Municipal Utilities"
        #         " Association: 2026 First Edition",
        #     style=PSTYLES["CoverTitle"].bold
        # )
        title_para = Paragraph(__trm_title__, style=PSTYLES["CoverTitle"].bold)
        _, mid_height = title_para.wrap(INNER_WIDTH, 0)
        data.append([                                                   #Draw a table to store the paragraph flowable ...
            Table(                                                      #...CoverSheetTotal: Add mid_table to a list of tables
                [[title_para]],
                style=TSTYLES["CoverMidContent"],
                hAlign="RIGHT"
            )
        ])

        # Build bottom content container (version and last updated date)
        version_container = VersionContainer()                                       #Version box: Get the text for the version #
        
        cpd_style = PSTYLES["CoverPreDate"].italic
        cd_style = PSTYLES["CoverDate"]
        cpd_text = "Last Updated  "                                                  #LastUpdate: Get the title text
        cpd_width = stringWidth(cpd_text, cpd_style.font_name, cpd_style.font_size)  #LastUpdated: Measure the width for the flowable
        cd_width = stringWidth(__trm_version_date__, cd_style.font_name, cd_style.font_size)     
        max_width = cpd_width + cd_width                                             
        date_table = Table(                                                          #LastUpdated: Draw a 1x2 table for the last updated text: title, date
            [[Paragraph(cpd_text, style=cpd_style.italic), Paragraph(__trm_version_date__, style=cd_style)]],
            colWidths=(cpd_width, cd_width),
            style=TSTYLES["CoverDateContent"],
            hAlign="RIGHT"
        )
        
        bottom_content = Table(                                                      #Together: Draw a 3x1 table for the version box and last updated
            [[version_container], [""], [date_table]],
            style=TSTYLES["CoverBottomContent"],
            colWidths=max_width,
            rowHeights=[version_container._height, 8, PSTYLES["CoverPreDate"].leading],
            hAlign="RIGHT"
        )
        
        data.append([bottom_content])                                  #CoverSheetTotal: Add bottom_table to a list of tables
        bottom_height = math.fsum(bottom_content._argH)

        # Build content container and apply vertical spacing
        rem_height = INNER_HEIGHT - top_height - mid_height - bottom_height
        data.insert(1, [""])                                          #Insert blank row b/w top & mid_table and b/w mid & bottom_table
        data.insert(3, [""])
        super().__init__([
            Table(                                                    #Generate the 1x1 table flowable (CoverSheet layout box) with everything together
                data,
                style=TSTYLES["CoverContent"],
                rowHeights=[
                    top_height,
                    rem_height * (1 / 3),
                    mid_height,
                    rem_height * (2 / 3),
                    bottom_height
                ],
                hAlign="RIGHT"
            )
        ])
