(function($){
  $(function(){

    var window_width = $(window).width();

    // convert rgb to hex value string
    function rgb2hex(rgb) {
      if (/^#[0-9A-F]{6}$/i.test(rgb)) { return rgb; }

      rgb = rgb.match(/^rgb\((\d+),\s*(\d+),\s*(\d+)\)$/);

      if (rgb === null) { return "N/A"; }

      function hex(x) {
          return ("0" + parseInt(x).toString(16)).slice(-2);
      }

      return "#" + hex(rgb[1]) + hex(rgb[2]) + hex(rgb[3]);
    }

    $('.dynamic-color .col').each(function () {
      $(this).children().each(function () {
        var color = $(this).css('background-color'),
            classes = $(this).attr('class');
        $(this).html(rgb2hex(color) + " " + classes);
        if (classes.indexOf("darken") >= 0 || $(this).hasClass('black')) {
          $(this).css('color', 'rgba(255,255,255,.9');
        }
      });
    });


    // Toggle Flow Text
    var toggleFlowTextButton = $('#flow-toggle');
    toggleFlowTextButton.click( function(){
      $('#flow-text-demo').children('p').each(function(){
          $(this).toggleClass('flow-text');
        });
    });

    // Detect touch screen and enable scrollbar if necessary
    function is_touch_device() {
      try {
        document.createEvent("TouchEvent");
        return true;
      } catch (e) {
        return false;
      }
    }
    if (is_touch_device()) {
      $('#nav-mobile').css({ overflow: 'auto'});
    }

    // Plugin initialization
    $('.carousel.carousel-slider').carousel({full_width: true});
    $('.carousel').carousel();
    $('.slider').slider({full_width: true});
    $('.parallax').parallax();
    $('.modal').modal();
    $('.scrollspy').scrollSpy();
    $('.button-collapse').sideNav({'edge': 'left', draggable: true});
    $('.datepicker').pickadate({selectYears: 20});
    $('select').not('.disabled').material_select();
    $('.materialboxed').materialbox();
    $('.chips').material_chip();
    $('.chips-initial').material_chip({
      readOnly: true
    });
    $('.chips-placeholder').material_chip({
      placeholder: 'Enter a tag',
      secondaryPlaceholder: '+Tag',
    });

  }); // end of document ready
})(jQuery); // end of jQuery name space
