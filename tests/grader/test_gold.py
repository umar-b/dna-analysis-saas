"""Tests for gold-set validation (issue #4)."""

from dna_analysis.grader.gold import read_genome_rsids, validate_gold
from dna_analysis.models import GoldEntry


def make_entry(rsid="rs4244285", gene="CYP2C19", drug="clopidogrel", actionable=True):
    return GoldEntry(
        rsid=rsid,
        gene=gene,
        drug=drug,
        guideline_id="PA166251443",
        evidence_level="A",
        clinically_actionable=actionable,
    )


def test_flags_rsid_absent_from_genome():
    gold = [make_entry(rsid="rs4244285"), make_entry(rsid="rs9999999")]
    result = validate_gold(
        gold, genome_rsids={"rs4244285"}, allowlist={"CYP2C19", "clopidogrel"}
    )
    assert "rs9999999" in result.missing_from_genome
    assert "rs4244285" not in result.missing_from_genome


def test_flags_drug_or_gene_outside_allowlist():
    gold = [make_entry(drug="madeupazole")]
    result = validate_gold(gold, genome_rsids={"rs4244285"}, allowlist={"CYP2C19"})
    assert "madeupazole" in result.out_of_allowlist


def test_coverage_mix_and_minimum():
    # 25 actionable + 2 unremarkable, all rsids present, all tokens allowed
    gold = [make_entry(actionable=True) for _ in range(25)]
    gold += [make_entry(actionable=False) for _ in range(2)]
    result = validate_gold(
        gold, genome_rsids={"rs4244285"}, allowlist={"CYP2C19", "clopidogrel"}
    )
    assert result.actionable_count == 25
    assert result.unremarkable_count == 2
    assert result.meets_minimum is True
    assert result.has_coverage_mix is True
    assert result.ok is True


def test_not_ok_when_too_few_or_no_unremarkable():
    gold = [make_entry(actionable=True) for _ in range(3)]
    result = validate_gold(
        gold, genome_rsids={"rs4244285"}, allowlist={"CYP2C19", "clopidogrel"}
    )
    assert result.meets_minimum is False
    assert result.has_coverage_mix is False
    assert result.ok is False


def test_read_genome_rsids_skips_comments():
    text = "# comment\nrs4244285\t10\t96541616\tGG\nrs1799853\t10\t96702047\tCC\n"
    assert read_genome_rsids(text) == {"rs4244285", "rs1799853"}
