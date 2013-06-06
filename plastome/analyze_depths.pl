use CircleGraph;
use File::Basename;
use File::Temp qw/ tempfile tempdir /;
use Getopt::Long;
use Pod::Usage;
require "subfuncs.pl";
require "circlegraphs.pl";

if (@ARGV == 0) {
    pod2usage(-verbose => 1);
}

my $runline = "running " . basename($0) . " " . join (" ", @ARGV) . "\n";

my ($samplefile, $gb_file, $labelfile, $outfile) = 0;
my $samplesize = 1000;
my $keepfiles = 0;
my $help = 0;
my $min_coverage = 0;
my $circle_size = 157033;


GetOptions ('samples|input=s' => \$samplefile,
            'outputfile=s' => \$outfile,
            'window:i' => \$samplesize,
            'labels:s' => \$labelfile,
            'genbank|gb:s' => \$gb_file,
            'keepfiles!' => \$keepfiles,
            'coverage:i' => \$min_coverage,
            'size:i' => \$circle_size,
            'help|?' => \$help) or pod2usage(-msg => "GetOptions failed.", -exitval => 2);

if ($help) {
    pod2usage(-verbose => 1);
}

print $runline;

my @names;
if ($samplefile =~ /(.+?)\.depth/) {
    $samplefile = $1;
    push @names, $samplefile;
} else {
    open FH, "<", "$samplefile" or die "no such file";
    my @rawnames = <FH>;
    close FH;

    # don't process blank names
    foreach my $name (@rawnames) {
        $name =~ s/\n//;
        if ($name !~ /^\s*$/) {
            push @names, $name;
        }
    }
}


# process the gb file
if ($gb_file) {
	if ($gb_file =~ /\.gb$/) {
        my ($fh, $filename) = tempfile(UNLINK => 1);
        my $gb_locs = get_locations_from_genbank_file($gb_file);
		print $fh $gb_locs;
		close $fh;
	    $gb_file = "$filename";

	    $gb_locs =~ /(.+)\n(.+?)$/;
	    my $source = $2;
	    $source =~ /.+?\t.+?\t(.+)$/;
	    $circle_size = $1;
	}
}


my $labels;
if ($labelfile) {
    $labels = make_label_lookup ($labelfile);
}

my %samples;
foreach my $name (@names) {
    my $depthfile = "$name".".depth";
    my $samplename = basename($name);
    print "processing $samplename\n";
    open VCF_FH, "<", "$depthfile" or die "couldn't open $depthfile";
    my @depths = ();
    my @indels = ();
    my $i = 1;
    my $in_indel = 0;
    my $line = readline VCF_FH;
    my $curr_indel_start = 0;

    #eat any header lines:
    while ($line =~ /#/) {
    	$line = readline VCF_FH;
    }

	$line =~ /\t(.*?)\t(.*?)\s/;
	if ($2 == 0) {
		$curr_indel_start = 1;
	}
    for ($i=1; $i <= $circle_size; $i++) {
        $line =~ /\t(.*?)\t(.*?)\s/;
        my $depth = $2;
        if ($i != $1) { # this position isn't listed in the depths file; assume it is 0
        	$depth = 0;
        } else {
			$line = readline VCF_FH;
        }
		if ($curr_indel_start) { # are we in an indel already?
			if ($depth > $min_coverage) { # we're not in an indel anymore; end the indel.
				push @indels, "$curr_indel_start\t$i";
				$curr_indel_start = 0;
			}
		} else { # we're not in an indel. Start one if the depth is 0.
			if ($depth <= $min_coverage) {
				$curr_indel_start = $i;
			}
		}
		push @depths, $depth;
    }
    close VCF_FH;
    if ($curr_indel_start) {
        push @indels, "$curr_indel_start\t".($i-1);
    }
    $samples{$samplename}{"depths"} = \@depths;
    $samples{$samplename}{"indels"} = \@indels;
}


while (($key, $value) = each %samples) {
    my @depth_array = @{$value->{"depths"}};
    open FH, ">", "$outfile"."_$key"."_depths.txt";
    print FH "pos\t$key\n";
    my $sum = 0;
    my $i;
    for ($i=1; $i<=@depth_array; $i++) {
        if ($samplesize) {
            if (($i%$samplesize)==0) {
                print FH "$i\t".@depth_array[$i-1]."\n";
            }
        } else {
            print FH "$i\t".@depth_array[$i-1]."\n";
        }
    }
    close FH;

    my @indel_array = @{$value->{"indels"}};
    open FH, ">", "$outfile"."_$key"."_indels.txt";
    my $sum = 0;
    my $i;
    for ($i=1; $i<=@indel_array; $i++) {
        print FH "$i\t".@indel_array[$i-1]."\n";
    }
    print FH "size\t1\t$circle_size\n";
    close FH;
}

print "drawing graphs...\n";
my $circlegraph_obj = new CircleGraph();
$circlegraph_obj->inner_radius($circlegraph_obj->inner_radius - 100);
my $max=1;
my %graphs;
while (($key, $value) = each %samples) {
    # process each depths file
    open FH, "<", "$outfile"."_$key"."_depths.txt";
    my @items = <FH>;
    close FH;
    my $header = shift @items;
    my (@xvals, @yvals);
    foreach my $line (@items) {
        $line =~ /(.*?)\t(.*?)\s/;
        push @xvals, $1;
        push @yvals, $2;
        if ($2 > $max) {
            $max = $2;
        }
    }
    if (!exists($graphs{"x"})) {
        $graphs{"x"} = \@xvals;
    }
    $graphs{$key} = \@yvals;
}

#process yvals so that they are scaled to 1
while (($key, $value) = each %samples) {
    my @yvals = @{$graphs{$key}};
    for (my $y=0;$y<@yvals;$y++) {
        @{$graphs{$key}}[$y] = @yvals[$y]/$max;
    }
}

my $j = 0;

# draw the gene map
if ($gb_file) {
	draw_gene_map ($gb_file, $circlegraph_obj, "OUT");
} else {
	$circlegraph_obj->set_font("Helvetica", 6, "black");
	for (my $i = 1000; $i < $circle_size; $i=$i+1000) {
		my $angle = ($i/$circle_size) * 360;
		my $radius = $circlegraph_obj->outer_radius + 10;
		my $label = $i;
		 $circlegraph_obj->circle_label($angle, $radius, "$label");
	}
}



# draw the coverage maps
my @xvals = @{$graphs{"x"}};
while (($key, $value) = each %samples) {
    my @yvals = @{$graphs{$key}};
    $circlegraph_obj->plot_line(\@xvals, \@yvals, {color=>$j});
    $j++;
}

$circlegraph_obj->draw_circle($circlegraph_obj->inner_radius);
$circlegraph_obj->draw_circle($circlegraph_obj->outer_radius);

print "drawing reference mismatch maps...\n";
# draw the indel maps
$j = 0;
$circlegraph_obj->inner_radius($circlegraph_obj->inner_radius - 150);
while (($key, $value) = each %samples) {
    $circlegraph_obj = draw_regions ( "$outfile"."_$key"."_indels.txt", $circlegraph_obj, $j, $circlegraph_obj->inner_radius + ($j*5));
    $j++;
}

$circlegraph_obj->draw_circle($circlegraph_obj->inner_radius-5);

# draw the labels
$j = 0;
while (($key, $value) = each %samples) {
    my $label = $key;
    if (exists $labels->{$key}) {
        $label = $labels->{$key};
    }
    #$circlegraph_obj->append_to_legend($label,$j);
    $j++;
}

$circlegraph_obj->append_to_legend("Maximum coverage was $max, scaled to 1");
$circlegraph_obj->append_to_legend("Minimum coverage was $min_coverage");
$circlegraph_obj->append_to_legend("Sampling frequency was $samplesize");
$circlegraph_obj->draw_legend_text({size => 10, height => 15});

open FH, ">", "$outfile.ps" or die "couldn't open $outfile.ps";
print FH $circlegraph_obj->output_ps();
close FH;

if (!$keepfiles) {
    while (($key, $value) = each %samples) {
        unlink "$outfile"."_$key"."_depths.txt" or warn "could not delete $outfile"."_$key"."_depths.txt";
        unlink "$outfile"."_$key"."_indels.txt" or warn "could not delete $outfile"."_$key"."_indels.txt";
    }
}

__END__

=head1 NAME

analyze_depths

=head1 SYNOPSIS

analyze_depths -samples -window -output [-genbank] [-labels]

=head1 OPTIONS

  -samples|input:   input file of samples with depth files to analyze
  -window:          sampling frequency (if not specified, 1000 bp)
  -outputfile:      prefix of output files
  -genbank|gb:      optional: genbank file to generate a map along the graph
  -labels:          optional: tab-delimited list of samples and their corresponding labels
  -keepfiles:       optional: keep data files that are created (default is no)
  -coverage:		optional: minimum level of coverage to call as missing.

=head1 DESCRIPTION

Graphs coverage depths using depth data generated from samtools mpileup.

=cut

