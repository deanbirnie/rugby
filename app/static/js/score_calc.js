// Score calculator: converts tries/conversions/penalties/drop goals into a
// total and writes it into the team's score field as you type.
(function () {
  function recalc(block) {
    var total = 0;
    var counts = {};
    block.querySelectorAll("[data-points]").forEach(function (input) {
      var n = parseInt(input.value, 10) || 0;
      total += n * parseInt(input.dataset.points, 10);
      counts[input.dataset.kind] = n;
    });

    block.querySelector(".calc-total").textContent = total;

    var target = document.getElementById(block.dataset.target);
    if (target) {
      target.value = total;
    }

    var warn = block.querySelector(".calc-warn");
    if (warn) {
      warn.hidden = !(counts.conversions > counts.tries);
    }
  }

  document.querySelectorAll(".calc-team").forEach(function (block) {
    block.querySelectorAll("[data-points]").forEach(function (input) {
      input.addEventListener("input", function () {
        recalc(block);
      });
    });
  });
})();
