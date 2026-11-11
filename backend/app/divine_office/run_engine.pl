#!/usr/bin/perl
# Runs Divinum Officium's own, unmodified officium.pl for ONE request and appends the day data it computed as a trailing comment.
# usage: perl run_engine.pl <horas directory> <query string>
use strict;
use warnings;

my ($dir, $query) = @ARGV;
die "usage: run_engine.pl <horas dir> <query>\n" unless defined $dir && defined $query;
chdir $dir or die "cannot enter $dir: $!\n";
@ARGV = ($query);
$0 = "$dir/officium.pl";    # the engine reads its own script name

END {
    binmode(STDOUT, ':utf8');
    no warnings 'once';
    print "\n<!--DO-META\t", join("\t", map { defined $_ ? $_ : '' } @main::dayname),
        "\twinner=", ($main::winner // ''), "\tcommemoratio=", ($main::commemoratio // ''), "\trank=", ($main::rank // ''), "-->\n";
    # The engine's own headline ("Name ~ rank"), and the English name of the winning office, for the liturgical calendar card.
    my $headline = eval { main::setheadline() } // '';
    my %english = eval { %{ main::setupstring('English', $main::winner) } };
    # The English [Rank] line carries the English name ("Name;;Duplex ...") where the English file has one; its [Officium] may be filled in from the Latin.
    my ($rank_name) = (($english{Rank} // '') =~ /^([^;\n]+);;/);
    my $officium = defined $rank_name && length $rank_name ? $rank_name : ($english{Officium} // '');
    $officium =~ s/;.*//s;
    # Where the engine's English data holds only the Latin title for this version (its 1960 [Rank] variant exists in the Latin file alone), fall back to the
    # English file's own default [Rank] name, read as written. Nothing is translated here.
    my ($latin_name) = split / ~ /, $headline;
    (my $same = $officium) =~ s/\s+//g;
    (my $latin_same = $latin_name // '') =~ s/\s+//g;
    if ((!length $officium || lc $same eq lc $latin_same) && ($main::winner // '') =~ m{^(?:Sancti|Tempora|Commune)/[\w\-]+\.txt$}) {
        if (open my $fh, '<:encoding(UTF-8)', "../../www/horas/English/$main::winner") {
            my $in_rank = 0;
            while (my $line = <$fh>) {
                chomp $line;
                if ($line =~ /^\[Rank\]\s*$/) { $in_rank = 1; next }
                if ($in_rank) { (my $name = $line) =~ s/;;.*//; $officium = $name if length $name; last }
            }
            close $fh;
        }
    }
    for ($headline, $officium) { s/[\t\r\n]+/ /g }
    print "<!--DO-HEAD\t$headline\t$officium-->\n";
}
do "./officium.pl";
print STDERR $@ if $@;
